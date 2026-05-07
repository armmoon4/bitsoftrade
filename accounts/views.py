import logging

logger = logging.getLogger(__name__)

from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

# New imports for Password Reset and Google Auth
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .models import User
from .serializers import (
    UserSerializer, 
    UserRegistrationSerializer, 
    UserLoginSerializer,
    UserProfileUpdateSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    GoogleLoginSerializer
)


def get_tokens_for_user(user):
    """Generate JWT tokens for user"""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


# ==========================================
# Existing Auth Views
# ==========================================

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_view(request):
    """User registration endpoint"""
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        tokens = get_tokens_for_user(user)
        return Response({
            'message': 'User registered successfully',
            'user': UserSerializer(user).data,
            'tokens': tokens
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """User login endpoint"""
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        user = authenticate(request, email=email, password=password)
        
        if user is not None:
            tokens = get_tokens_for_user(user)
            return Response({
                'message': 'Login successful',
                'user': UserSerializer(user).data,
                'tokens': tokens
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Invalid email or password'
            }, status=status.HTTP_401_UNAUTHORIZED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    """User logout endpoint"""
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    except Exception:
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_user_view(request):
    """Get current logged-in user details"""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def profile_view(request):
    """Get or update user profile"""
    if request.method == 'GET':
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    
    elif request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        serializer = UserProfileUpdateSerializer(
            request.user, 
            data=request.data, 
            partial=partial
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Profile updated successfully',
                'user': UserSerializer(request.user).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# New Password Management Views
# ==========================================

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password_view(request):
    """Allows authenticated users to change their password."""
    serializer = ChangePasswordSerializer(data=request.data)
    if serializer.is_valid():
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'old_password': ['Wrong password.']}, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'message': 'Password updated successfully'}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def request_password_reset(request):
    """Generates a password reset link and sends it via the branded HTML email template."""
    serializer = PasswordResetRequestSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        user = User.objects.filter(email=email).first()
        
        if user:
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            # Build the frontend reset URL
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://bits-of-trade.vercel.app')
            reset_link = f"{frontend_url}/reset-password?uid={uidb64}&token={token}"

            # Personalised greeting — use first name if available
            first_name = (user.first_name or '').strip()
            user_name = f' {first_name}' if first_name else ''

            try:
                # Render the branded HTML template
                html_message = render_to_string(
                    'notifications/password_reset_email.html',
                    {
                        'user_name': user_name,
                        'reset_link': reset_link,
                    }
                )

                send_mail(
                    subject='Reset Your Password — BitsOfTrade',
                    message=(
                        f'Hi{user_name},\n\n'
                        f'Click the link below to reset your password:\n\n{reset_link}\n\n'
                        'This link expires in 24 hours.\n\n'
                        'If you did not request this, please ignore this email.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                logger.info(f'[PasswordReset] Reset email sent to {user.email}')

            except Exception as exc:
                logger.error(f'[PasswordReset] Failed to send email to {user.email}: {exc}')
                # In DEBUG mode expose the real error so you can fix it fast
                if settings.DEBUG:
                    return Response(
                        {'error': f'Email sending failed: {str(exc)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

        return Response({'message': 'If an account with that email exists, a reset link has been sent.'}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def confirm_password_reset(request):
    """Verifies the token from the URL and sets the new password."""
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if serializer.is_valid():
        uidb64 = serializer.validated_data['uidb64']
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']
        
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.set_password(new_password)
            user.save()
            return Response({'message': 'Password reset successful.'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
            
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# New Google Sign-In View
# ==========================================

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def google_login_view(request):
    """Verifies Google ID token, creates user if needed, and returns JWTs."""
    serializer = GoogleLoginSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data['token']
        
        try:
            CLIENT_ID = getattr(settings, 'GOOGLE_OAUTH2_CLIENT_ID', None)
            if not CLIENT_ID:
                return Response({'error': 'Google Client ID not configured on server'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), CLIENT_ID)
            
            email = idinfo['email']
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')
            
            user, created = User.objects.get_or_create(email=email)
            
            if created:
                user.first_name = first_name
                user.last_name = last_name
                user.set_unusable_password() #use Google to login, so no local password
                user.save()
            
            tokens = get_tokens_for_user(user)
            
            return Response({
                'message': 'Google Login successful',
                'user': UserSerializer(user).data,
                'tokens': tokens,
                'is_new_user': created
            }, status=status.HTTP_200_OK)
            
        except ValueError:
            return Response({'error': 'Invalid Google token'}, status=status.HTTP_400_BAD_REQUEST)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ==========================================
# Onboarding
# ==========================================

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def complete_onboarding_view(request):
    """Mark onboarding as completed for the current user."""
    request.user.onboarding_completed = True
    request.user.save(update_fields=['onboarding_completed'])
    return Response({'message': 'Onboarding completed'}, status=status.HTTP_200_OK)



@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_user_view(request):
    """Get current logged-in user details with active discipline session state."""
    from discipline.models import DisciplineSession
    from django.utils.timezone import localdate

    user = request.user

    active_session = (
        DisciplineSession.objects
        .filter(user=user, session_state='red')
        .order_by('-session_date')
        .first()
    ) or (
        DisciplineSession.objects
        .filter(user=user, session_state='yellow')
        .order_by('-session_date')
        .first()
    ) or (
        DisciplineSession.objects
        .filter(user=user, session_date=localdate())
        .first()
    )

    serializer = UserSerializer(user, context={'active_session': active_session})
    return Response(serializer.data)


#Permanent delete 

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_account_view(request):
    """Permanently delete the authenticated user's account and all associated data."""
    user = request.user
    password = request.data.get('password')

    if not password:
        return Response(
            {'error': 'Password is required to confirm account deletion.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not user.check_password(password):
        return Response(
            {'error': 'Incorrect password. Account deletion cancelled.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Blacklist the refresh token if provided
    refresh_token = request.data.get('refresh')
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            pass  # Still proceed with deletion even if blacklisting fails

    # This cascades and deletes all related data (journal entries, trades, etc.)
    user.delete()

    return Response(
        {'message': 'Your account and all associated data have been permanently deleted.'},
        status=status.HTTP_200_OK
    )