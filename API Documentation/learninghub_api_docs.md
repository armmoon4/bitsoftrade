# LearningHub API Documentation

> **Base URL:** `/api/learninghub/`  
> **Authentication:** JWT Bearer Token  
> **Content-Type:** `application/json` (except file uploads: `multipart/form-data`)

---

## Table of Contents

1. [Authentication](#authentication)
2. [Learning Lessons](#learning-lessons)
3. [Courses](#courses)
4. [Videos](#videos)
5. [User Course Progress](#user-course-progress)
6. [Data Models](#data-models)
7. [Error Responses](#error-responses)

---

## Authentication

All endpoints require a valid JWT Bearer token in the `Authorization` header.

```
Authorization: Bearer <your_jwt_token>
```

Two types of tokens are supported:

| Token Type | Payload Fields | Access Level |
|---|---|---|
| **User Token** | `user_id` | Read-only (GET) on most endpoints |
| **Admin Token** | `is_admin: true`, `admin_id` | Full access (GET, POST, PUT, PATCH, DELETE) |

> **Note:** The `UserCourseProgress` endpoints use Django's `IsAuthenticated` permission and expect a standard user session/token.

---

## Learning Lessons

A **LearningLesson** is the top-level grouping entity. Each lesson contains multiple courses.

### Endpoints

| Method | URL | Permission | Description |
|---|---|---|---|
| `GET` | `/learning-lessons/` | User or Admin | List all learning lessons |
| `POST` | `/learning-lessons/` | Admin only | Create a new learning lesson |
| `GET` | `/learning-lessons/{id}/` | User or Admin | Retrieve a learning lesson |
| `PUT` | `/learning-lessons/{id}/` | Admin only | Full update a learning lesson |
| `PATCH` | `/learning-lessons/{id}/` | Admin only | Partial update a learning lesson |
| `DELETE` | `/learning-lessons/{id}/` | Admin only | Delete a learning lesson |

---

### GET `/learning-lessons/`

Returns a list of all learning lessons with their nested courses.

**Request**
```http
GET /api/learninghub/learning-lessons/
Authorization: Bearer <token>
```

**Response `200 OK`**
```json
[
  {
    "id": 1,
    "title": "Introduction to Programming",
    "description": "Learn the basics of programming concepts.",
    "is_active": true,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z",
    "courses": [
      {
        "id": 1,
        "title": "Python Fundamentals",
        "about": "A beginner-friendly Python course.",
        "description": "Covers variables, loops, functions, and more.",
        "course_type": "general",
        "course_level": "beginner",
        "is_active": true,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
        "lessons": {
          "id": 1,
          "title": "Introduction to Programming",
          "description": "Learn the basics of programming concepts."
        },
        "videos": [
          {
            "id": 1,
            "title": "Setting Up Python",
            "description": "Install Python and set up your environment.",
            "video": "/media/LearningLesson/Course/videos/setup.mp4",
            "course": {
              "id": 1,
              "title": "Python Fundamentals",
              "course_type": "general",
              "course_level": "beginner"
            },
            "is_free": true,
            "is_complete": false,
            "is_active": true,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z"
          }
        ]
      }
    ]
  }
]
```

---

### POST `/learning-lessons/`

Create a new learning lesson. **Admin token required.**

**Request**
```http
POST /api/learninghub/learning-lessons/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body**
```json
{
  "title": "Introduction to Programming",
  "description": "Learn the basics of programming concepts.",
  "is_active": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | ✅ Yes | Title of the lesson (max 255 chars) |
| `description` | string | ❌ No | Detailed description |
| `is_active` | boolean | ❌ No | Defaults to `true` |

**Response `201 Created`**
```json
{
  "message": "Learning Lesson created successfully",
  "learning_lesson": {
    "id": 2,
    "title": "Introduction to Programming",
    "description": "Learn the basics of programming concepts.",
    "is_active": true,
    "created_at": "2024-01-20T08:00:00Z",
    "updated_at": "2024-01-20T08:00:00Z",
    "courses": []
  }
}
```

---

### GET `/learning-lessons/{id}/`

Retrieve a single learning lesson by its ID.

**Request**
```http
GET /api/learninghub/learning-lessons/1/
Authorization: Bearer <token>
```

**Response `200 OK`**
```json
{
  "id": 1,
  "title": "Introduction to Programming",
  "description": "Learn the basics of programming concepts.",
  "is_active": true,
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "courses": [ ... ]
}
```

---

### PUT `/learning-lessons/{id}/`

Fully update a learning lesson. All fields must be provided. **Admin token required.**

**Request**
```http
PUT /api/learninghub/learning-lessons/1/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body**
```json
{
  "title": "Updated Lesson Title",
  "description": "Updated description.",
  "is_active": true
}
```

**Response `200 OK`**
```json
{
  "message": "Learning Lesson updated successfully",
  "learning_lesson": {
    "id": 1,
    "title": "Updated Lesson Title",
    ...
  }
}
```

---

### PATCH `/learning-lessons/{id}/`

Partially update a learning lesson. Only send the fields you want to change. **Admin token required.**

**Request**
```http
PATCH /api/learninghub/learning-lessons/1/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body** *(example: deactivating a lesson)*
```json
{
  "is_active": false
}
```

**Response `200 OK`**
```json
{
  "message": "Learning Lesson updated successfully",
  "learning_lesson": { ... }
}
```

---

### DELETE `/learning-lessons/{id}/`

Delete a learning lesson permanently. **Admin token required.**

> ⚠️ **Warning:** Deleting a lesson will cascade-delete all associated courses and their videos.

**Request**
```http
DELETE /api/learninghub/learning-lessons/1/
Authorization: Bearer <admin_token>
```

**Response `204 No Content`**
```json
{
  "message": "Learning Lesson deleted successfully"
}
```

---

## Courses

A **Course** belongs to a single **LearningLesson** and contains multiple **Videos**.

### Endpoints

| Method | URL | Permission | Description |
|---|---|---|---|
| `GET` | `/courses/` | User or Admin | List all courses |
| `POST` | `/courses/` | Admin only | Create a new course |
| `GET` | `/courses/{id}/` | User or Admin | Retrieve a course |
| `PUT` | `/courses/{id}/` | Admin only | Full update a course |
| `PATCH` | `/courses/{id}/` | Admin only | Partial update a course |
| `DELETE` | `/courses/{id}/` | Admin only | Delete a course |

---

### GET `/courses/`

Returns a list of all courses with nested lesson info and videos.

**Request**
```http
GET /api/learninghub/courses/
Authorization: Bearer <token>
```

**Response `200 OK`**
```json
[
  {
    "id": 1,
    "title": "Python Fundamentals",
    "about": "A beginner-friendly Python course.",
    "description": "Covers variables, loops, functions, and more.",
    "course_type": "general",
    "course_level": "beginner",
    "is_active": true,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z",
    "lessons": {
      "id": 1,
      "title": "Introduction to Programming",
      "description": "Learn the basics of programming concepts."
    },
    "videos": [
      {
        "id": 1,
        "title": "Setting Up Python",
        "description": "Install Python and set up your environment.",
        "video": "/media/LearningLesson/Course/videos/setup.mp4",
        "course": {
          "id": 1,
          "title": "Python Fundamentals",
          "course_type": "general",
          "course_level": "beginner"
        },
        "is_free": true,
        "is_complete": false,
        "is_active": true,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z"
      }
    ]
  }
]
```

---

### POST `/courses/`

Create a new course. **Admin token required.**

**Request**
```http
POST /api/learninghub/courses/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body**
```json
{
  "title": "Python Fundamentals",
  "about": "A beginner-friendly Python course.",
  "description": "Covers variables, loops, functions, and more.",
  "lessons": 1,
  "course_type": "general",
  "course_level": "beginner",
  "is_active": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | ✅ Yes | Course title (max 255 chars) |
| `lessons` | integer | ✅ Yes | ID of the parent `LearningLesson` |
| `about` | string | ❌ No | Short summary of the course |
| `description` | string | ❌ No | Full course description |
| `course_type` | string | ❌ No | Defaults to `"general"` |
| `course_level` | string | ❌ No | Defaults to `"beginner"` |
| `is_active` | boolean | ❌ No | Defaults to `true` |

**Response `201 Created`**
```json
{
  "message": "Course created successfully",
  "course": {
    "id": 2,
    "title": "Python Fundamentals",
    "about": "A beginner-friendly Python course.",
    "description": "Covers variables, loops, functions, and more.",
    "course_type": "general",
    "course_level": "beginner",
    "is_active": true,
    "created_at": "2024-01-20T08:00:00Z",
    "updated_at": "2024-01-20T08:00:00Z",
    "lessons": {
      "id": 1,
      "title": "Introduction to Programming",
      "description": "Learn the basics of programming concepts."
    },
    "videos": []
  }
}
```

---

### GET `/courses/{id}/`

Retrieve a single course by its ID.

**Request**
```http
GET /api/learninghub/courses/1/
Authorization: Bearer <token>
```

**Response `200 OK`** — same structure as list item above.

---

### PUT `/courses/{id}/`

Fully update a course. All required fields must be provided. **Admin token required.**

**Request**
```http
PUT /api/learninghub/courses/1/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body**
```json
{
  "title": "Advanced Python",
  "about": "Deep dive into Python.",
  "description": "OOP, decorators, async programming.",
  "lessons": 1,
  "course_type": "advanced",
  "course_level": "advanced",
  "is_active": true
}
```

**Response `200 OK`**
```json
{
  "message": "Course updated successfully",
  "course": { ... }
}
```

---

### PATCH `/courses/{id}/`

Partially update a course. **Admin token required.**

**Request**
```http
PATCH /api/learninghub/courses/1/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body** *(example: change course level)*
```json
{
  "course_level": "intermediate"
}
```

**Response `200 OK`**
```json
{
  "message": "Course updated successfully",
  "course": { ... }
}
```

---

### DELETE `/courses/{id}/`

Delete a course permanently. **Admin token required.**

> ⚠️ **Warning:** Deleting a course will cascade-delete all associated videos and user progress records.

**Request**
```http
DELETE /api/learninghub/courses/1/
Authorization: Bearer <admin_token>
```

**Response `204 No Content`**
```json
{
  "message": "Course deleted successfully"
}
```

---

## Videos

A **Video** belongs to a single **Course**. Uploaded as files via `multipart/form-data`.

### Endpoints

| Method | URL | Permission | Description |
|---|---|---|---|
| `GET` | `/videos/` | User or Admin | List all videos |
| `POST` | `/videos/` | Admin only | Upload a new video |
| `GET` | `/videos/{id}/` | User or Admin | Retrieve a video |
| `PUT` | `/videos/{id}/` | Admin only | Full update a video |
| `PATCH` | `/videos/{id}/` | Admin only | Partial update a video |
| `DELETE` | `/videos/{id}/` | Admin only | Delete a video |

---

### GET `/videos/`

Returns a list of all videos with their associated course details.

**Request**
```http
GET /api/learninghub/videos/
Authorization: Bearer <token>
```

**Response `200 OK`**
```json
[
  {
    "id": 1,
    "title": "Setting Up Python",
    "description": "Install Python and configure your environment.",
    "video": "/media/LearningLesson/Course/videos/setup.mp4",
    "course": {
      "id": 1,
      "title": "Python Fundamentals",
      "course_type": "general",
      "course_level": "beginner"
    },
    "is_free": true,
    "is_complete": false,
    "is_active": true,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z"
  }
]
```

---

### POST `/videos/`

Upload a new video file. Must use `multipart/form-data`. **Admin token required.**

**Request**
```http
POST /api/learninghub/videos/
Authorization: Bearer <admin_token>
Content-Type: multipart/form-data
```

**Form Fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | ✅ Yes | Video title (max 255 chars) |
| `video` | file | ✅ Yes | The video file to upload |
| `course` | integer | ✅ Yes | ID of the parent `Course` |
| `description` | string | ❌ No | Description of the video |
| `is_free` | boolean | ❌ No | Whether the video is freely accessible. Defaults to `false` |
| `is_complete` | boolean | ❌ No | Whether the video is fully produced. Defaults to `false` |
| `is_active` | boolean | ❌ No | Whether the video is visible. Defaults to `true` |

**Example (using fetch)**
```javascript
const formData = new FormData();
formData.append("title", "Setting Up Python");
formData.append("video", videoFile);  // File object
formData.append("course", 1);
formData.append("is_free", true);

const response = await fetch("/api/learninghub/videos/", {
  method: "POST",
  headers: {
    "Authorization": "Bearer <admin_token>"
  },
  body: formData
});
```

**Response `201 Created`**
```json
{
  "message": "Video created successfully",
  "video": {
    "id": 3,
    "title": "Setting Up Python",
    "description": null,
    "video": "/media/LearningLesson/Course/videos/setup.mp4",
    "course": {
      "id": 1,
      "title": "Python Fundamentals",
      "course_type": "general",
      "course_level": "beginner"
    },
    "is_free": true,
    "is_complete": false,
    "is_active": true,
    "created_at": "2024-01-20T08:00:00Z",
    "updated_at": "2024-01-20T08:00:00Z"
  }
}
```

---

### GET `/videos/{id}/`

Retrieve a single video by its ID.

**Request**
```http
GET /api/learninghub/videos/1/
Authorization: Bearer <token>
```

**Response `200 OK`** — same structure as list item above.

---

### PUT `/videos/{id}/`

Fully update a video. All required fields must be provided. **Admin token required.**

**Request**
```http
PUT /api/learninghub/videos/1/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body**
```json
{
  "title": "Updated Video Title",
  "description": "Updated description.",
  "course": 1,
  "is_free": false,
  "is_complete": true,
  "is_active": true
}
```

> **Note:** To replace the video file itself, use `multipart/form-data` and include the `video` field.

**Response `200 OK`**
```json
{
  "message": "Video updated successfully",
  "video": { ... }
}
```

---

### PATCH `/videos/{id}/`

Partially update a video. **Admin token required.**

**Request**
```http
PATCH /api/learninghub/videos/1/
Authorization: Bearer <admin_token>
Content-Type: application/json
```

**Request Body** *(example: mark a video as complete)*
```json
{
  "is_complete": true
}
```

**Response `200 OK`**
```json
{
  "message": "Video updated successfully",
  "video": { ... }
}
```

---

### DELETE `/videos/{id}/`

Delete a video permanently. **Admin token required.**

**Request**
```http
DELETE /api/learninghub/videos/1/
Authorization: Bearer <admin_token>
```

**Response `204 No Content`**
```json
{
  "message": "Video deleted successfully"
}
```

---

## User Course Progress

Tracks a user's progress through a course, including which videos they've watched and their overall completion percentage.

### Endpoints

| Method | URL | Permission | Description |
|---|---|---|---|
| `GET` | `/course-progress/` | Authenticated User | List all course progress records |
| `POST` | `/course-progress/create/` | Authenticated User | Start tracking progress for a course |

---

### GET `/course-progress/`

Returns all user course progress records with detailed progress stats.

**Request**
```http
GET /api/learninghub/course-progress/
Authorization: Bearer <user_token>
```

**Response `200 OK`**
```json
[
  {
    "id": 1,
    "user": {
      "id": 42,
      "email": "user@example.com"
    },
    "course": {
      "id": 1,
      "title": "Python Fundamentals",
      "course_type": "general",
      "course_level": "beginner"
    },
    "videos_watched": [
      {
        "id": 1,
        "title": "Setting Up Python"
      },
      {
        "id": 2,
        "title": "Variables and Data Types"
      }
    ],
    "started_at": "2024-01-18T09:00:00Z",
    "completed_at": null,
    "completion_percentage": 50.0,
    "total_videos": 4,
    "completed_videos": 2,
    "is_completed": false,
    "total_UserCourseStart": 120,
    "total_completed_UserCourseStart": 34
  }
]
```

**Response Fields**

| Field | Type | Description |
|---|---|---|
| `id` | integer | Progress record ID |
| `user` | object | User's `id` and `email` |
| `course` | object | Course's `id`, `title`, `course_type`, `course_level` |
| `videos_watched` | array | List of watched videos with `id` and `title` |
| `started_at` | datetime | When the user started the course |
| `completed_at` | datetime or null | When the course was completed (null if not yet) |
| `completion_percentage` | float | Percentage of videos watched (0.0 – 100.0) |
| `total_videos` | integer | Total number of videos in the course |
| `completed_videos` | integer | Number of videos the user has watched |
| `is_completed` | boolean | Whether the user has watched all videos |
| `total_UserCourseStart` | integer | Total number of course progress records across all users |
| `total_completed_UserCourseStart` | integer | Total number of fully completed courses across all users |

---

### POST `/course-progress/create/`

Start tracking a user's progress for a specific course. Creates a new progress record.

> **Note:** Each user can only have one progress record per course (`unique_together` constraint on `user` + `course`). Attempting to create a duplicate will return a `400` error.

**Request**
```http
POST /api/learninghub/course-progress/create/
Authorization: Bearer <user_token>
Content-Type: application/json
```

**Request Body**
```json
{
  "user": 42,
  "course": 1
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `user` | integer | ✅ Yes | ID of the user enrolling |
| `course` | integer | ✅ Yes | ID of the course to track |

**Response `201 Created`**
```json
{
  "message": "Course progress created successfully",
  "course_progress": {
    "user": 42,
    "course": 1
  }
}
```

---

## Data Models

### LearningLesson

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto-generated primary key |
| `title` | string | Lesson title |
| `description` | string or null | Optional description |
| `is_active` | boolean | Whether lesson is visible (default: `true`) |
| `created_at` | datetime | Auto-set on creation |
| `updated_at` | datetime | Auto-updated on save |
| `courses` | array | Related courses (via `courses` related name) |

### Course

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto-generated primary key |
| `title` | string | Course title |
| `about` | string or null | Short summary |
| `description` | string or null | Full description |
| `lessons` | FK → LearningLesson | Parent lesson (`CASCADE` on delete) |
| `course_type` | string | Type label (default: `"general"`) |
| `course_level` | string | Difficulty label (default: `"beginner"`) |
| `is_active` | boolean | Visibility flag (default: `true`) |
| `created_at` | datetime | Auto-set on creation |
| `updated_at` | datetime | Auto-updated on save |
| `videos` | array | Related videos (via `videos` related name) |

### Video

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto-generated primary key |
| `title` | string | Video title |
| `description` | string or null | Optional description |
| `video` | file | Stored at `LearningLesson/Course/videos/` |
| `course` | FK → Course | Parent course (`CASCADE` on delete) |
| `is_free` | boolean | Free preview flag (default: `false`) |
| `is_complete` | boolean | Production status (default: `false`) |
| `is_active` | boolean | Visibility flag (default: `true`) |
| `created_at` | datetime | Auto-set on creation |
| `updated_at` | datetime | Auto-updated on save |

### UserCourseProgress

| Field | Type | Description |
|---|---|---|
| `id` | integer | Auto-generated primary key |
| `user` | FK → User | The enrolled user |
| `course` | FK → Course | The course being tracked |
| `videos_watched` | M2M → Video | Videos the user has watched |
| `started_at` | datetime | Auto-set when record is created |
| `completed_at` | datetime or null | Set when all videos are watched |
| `completion_percentage` | computed | `(watched / total) * 100` |

> `unique_together` constraint: `(user, course)` — one record per user per course.

---

## Error Responses

### `400 Bad Request`

Returned when request data is invalid (missing required fields, type errors, duplicate records, etc.).

```json
{
  "field_name": [
    "This field is required."
  ]
}
```

**Example — duplicate course progress:**
```json
{
  "non_field_errors": [
    "The fields user, course must make a unique set."
  ]
}
```

---

### `401 Unauthorized`

Returned when no token is provided or the token is invalid/expired.

```json
{
  "detail": "Authentication credentials were not provided."
}
```

---

### `403 Forbidden`

Returned when a user token attempts an admin-only operation (POST, PUT, PATCH, DELETE on courses, lessons, or videos).

```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

### `404 Not Found`

Returned when the requested resource does not exist.

```json
{
  "detail": "Not found."
}
```

---

## Quick Reference

### Headers

```
Authorization: Bearer <token>
Content-Type: application/json          ← for all JSON requests
Content-Type: multipart/form-data       ← for video uploads only
```

### Access Matrix

| Endpoint | User (GET) | User (Write) | Admin (GET) | Admin (Write) |
|---|:---:|:---:|:---:|:---:|
| `/learning-lessons/` | ✅ | ❌ | ✅ | ✅ |
| `/courses/` | ✅ | ❌ | ✅ | ✅ |
| `/videos/` | ✅ | ❌ | ✅ | ✅ |
| `/course-progress/` | ✅ | ✅ | ✅ | ✅ |

### Cascade Deletion Reference

```
LearningLesson
  └── Course (CASCADE)
        └── Video (CASCADE)
        └── UserCourseProgress (CASCADE)
```

> Deleting a `LearningLesson` will remove all its courses, videos, and user progress records.
