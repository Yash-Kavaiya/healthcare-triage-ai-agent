# User Management Dashboard - Implementation Guide

## Overview
A comprehensive admin dashboard has been added to manage users, view statistics, and control access across the Healthcare Triage AI Agent platform.

## Features Implemented

### Backend API Endpoints (Admin Only)
- `GET /api/v1/users` - List all users with their details
- `POST /api/v1/users` - Create a new user
- `PUT /api/v1/users/{username}` - Update user details (role, full name)
- `POST /api/v1/users/{username}/reset-password` - Admin reset user password
- `DELETE /api/v1/users/{username}` - Delete a user (cannot delete default users)

### Frontend User Management Page
Located at: `/admin/users` (Admin role only)

#### Dashboard Statistics
- **Admin Count** - Total administrators
- **Nurse Count** - Total nurses  
- **Operations Count** - Total operations staff
- **Total Users** - All users in the system

#### User Management Table
Displays all users with:
- Username (with "You" badge for current user)
- Full Name
- Role (color-coded badges)
- Status (Active / Password Reset Required)
- Onboarding Status (Completed / Pending)
- Action buttons for each user

#### Available Actions
1. **Edit User** ✏️ - Update full name and role
2. **Reset Password** 🔑 - Set new password (forces change on next login)
3. **Reset Onboarding** 🔄 - Reset onboarding status
4. **Delete User** 🗑️ - Remove user (disabled for current user and default users)

#### Create New User
- Username (required, unique)
- Password (required, min 8 characters)
- Full Name (optional)
- Role (operations, nurse, admin)
- New users require password change on first login

## Access

### From Admin Board
Click the **"👥 User Management"** button on the admin board page to access the dashboard.

### Direct URL
Navigate to: `http://localhost:4201/admin/users`

## Security Features
- Admin role required for all user management operations
- Cannot delete yourself
- Cannot delete default system users (admin, nurse, ops)
- Password reset forces user to change password on next login
- All sessions revoked when password is reset

## API Usage Examples

### List Users
```bash
GET /api/v1/users
Authorization: Bearer <admin_token>
```

### Create User
```bash
POST /api/v1/users
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "username": "doctor1",
  "password": "SecurePass123",
  "role": "nurse",
  "full_name": "Dr. Jane Smith"
}
```

### Reset Password
```bash
POST /api/v1/users/doctor1/reset-password
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "username": "doctor1",
  "new_password": "NewSecurePass456"
}
```

### Update User
```bash
PUT /api/v1/users/doctor1
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "full_name": "Dr. Jane Smith-Johnson",
  "role": "admin"
}
```

### Delete User
```bash
DELETE /api/v1/users/doctor1
Authorization: Bearer <admin_token>
```

## Database Schema
User data is stored in the `auth_users` table with:
- username (primary key)
- password_hash (PBKDF2-SHA256)
- role (operations, nurse, admin)
- full_name
- password_change_required (boolean)
- onboarding_completed (boolean)
- is_default (boolean, prevents deletion)
- created_at, updated_at timestamps

## Testing
1. Login as admin: `admin / admin123`
2. Navigate to Admin Board
3. Click "👥 User Management"
4. Test creating, editing, and managing users

## Notes
- All user management operations are logged in the audit trail
- Password changes revoke all active sessions for that user
- The dashboard auto-refreshes when actions are completed
- Responsive design works on mobile and desktop
