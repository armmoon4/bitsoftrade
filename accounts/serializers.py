from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from discipline.models import DisciplineSession
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """User serializer"""
    session_state = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'subscription_type', 'profile_picture', 'created_at', 'onboarding_completed', 'session_state']
        read_only_fields = ['id', 'created_at']

    def get_session_state(self, obj):
        active_session = self.context.get('active_session')
        if active_session:
            return active_session.session_state
        return None



class UserRegistrationSerializer(serializers.ModelSerializer):
    """User registration serializer"""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ['email', 'password', 'password_confirm', 'first_name', 'last_name']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class UserLoginSerializer(serializers.Serializer):
    """User login serializer"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """User profile update serializer"""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'profile_picture']


# ==========================================
# New Password & Auth Serializers
# ==========================================

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])


class GoogleLoginSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)