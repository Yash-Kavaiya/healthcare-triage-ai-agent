import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../api.service.js';
import {
  AuthUser,
  UserCreateRequest,
  UserUpdateRequest,
  AdminResetPasswordRequest,
} from '../api.types.js';

@Component({
  selector: 'app-user-management-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="user-management-container">
      <header class="page-header">
        <div class="header-content">
          <h1>User Management Dashboard</h1>
          <div class="header-actions">
            <button class="btn-secondary" (click)="refreshData()">
              <span class="icon">🔄</span> Refresh
            </button>
            <button class="btn-primary" (click)="showCreateModal()">
              <span class="icon">➕</span> Add User
            </button>
            <button class="btn-logout" (click)="logout()">Logout</button>
          </div>
        </div>
      </header>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon admin">👑</div>
          <div class="stat-content">
            <div class="stat-value">{{ adminCount }}</div>
            <div class="stat-label">Administrators</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon nurse">👩‍⚕️</div>
          <div class="stat-content">
            <div class="stat-value">{{ nurseCount }}</div>
            <div class="stat-label">Nurses</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon ops">📋</div>
          <div class="stat-content">
            <div class="stat-value">{{ opsCount }}</div>
            <div class="stat-label">Operations</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon total">👥</div>
          <div class="stat-content">
            <div class="stat-value">{{ totalUsers }}</div>
            <div class="stat-label">Total Users</div>
          </div>
        </div>
      </div>

      <div class="users-section">
        <h2>All Users</h2>
        <div class="table-container">
          <table class="users-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Full Name</th>
                <th>Role</th>
                <th>Status</th>
                <th>Onboarding</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr *ngFor="let user of users" [class.highlight]="user.username === currentUsername">
                <td>
                  <strong>{{ user.username }}</strong>
                  <span *ngIf="user.username === currentUsername" class="badge-current">You</span>
                </td>
                <td>{{ user.full_name || '—' }}</td>
                <td>
                  <span class="role-badge" [class]="user.role">
                    {{ getRoleDisplay(user.role) }}
                  </span>
                </td>
                <td>
                  <span
                    class="status-badge"
                    [class.warning]="user.password_change_required"
                    [class.success]="!user.password_change_required"
                  >
                    {{ user.password_change_required ? 'Password Reset Required' : 'Active' }}
                  </span>
                </td>
                <td>
                  <span
                    class="status-badge"
                    [class.success]="user.onboarding_completed"
                    [class.warning]="!user.onboarding_completed"
                  >
                    {{ user.onboarding_completed ? 'Completed' : 'Pending' }}
                  </span>
                </td>
                <td>
                  <div class="action-buttons">
                    <button
                      class="btn-action btn-edit"
                      (click)="showEditModal(user)"
                      title="Edit User"
                    >
                      ✏️
                    </button>
                    <button
                      class="btn-action btn-reset"
                      (click)="showResetPasswordModal(user)"
                      title="Reset Password"
                    >
                      🔑
                    </button>
                    <button
                      class="btn-action btn-onboard"
                      (click)="resetOnboarding(user)"
                      [disabled]="!user.onboarding_completed"
                      title="Reset Onboarding"
                    >
                      🔄
                    </button>
                    <button
                      class="btn-action btn-delete"
                      (click)="showDeleteModal(user)"
                      [disabled]="user.username === currentUsername"
                      title="Delete User"
                    >
                      🗑️
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Create User Modal -->
      <div class="modal" *ngIf="showModal && modalMode === 'create'" (click)="closeModal()">
        <div class="modal-content" (click)="$event.stopPropagation()">
          <div class="modal-header">
            <h3>Create New User</h3>
            <button class="modal-close" (click)="closeModal()">✕</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Username *</label>
              <input
                type="text"
                [(ngModel)]="createForm.username"
                placeholder="Enter username"
                class="form-input"
              />
            </div>
            <div class="form-group">
              <label>Password *</label>
              <input
                type="password"
                [(ngModel)]="createForm.password"
                placeholder="Minimum 8 characters"
                class="form-input"
              />
            </div>
            <div class="form-group">
              <label>Full Name</label>
              <input
                type="text"
                [(ngModel)]="createForm.full_name"
                placeholder="Enter full name"
                class="form-input"
              />
            </div>
            <div class="form-group">
              <label>Role *</label>
              <select [(ngModel)]="createForm.role" class="form-input">
                <option value="operations">Operations</option>
                <option value="nurse">Nurse</option>
                <option value="admin">Administrator</option>
              </select>
            </div>
            <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" (click)="closeModal()">Cancel</button>
            <button class="btn-primary" (click)="createUser()" [disabled]="isLoading">
              {{ isLoading ? 'Creating...' : 'Create User' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Edit User Modal -->
      <div class="modal" *ngIf="showModal && modalMode === 'edit'" (click)="closeModal()">
        <div class="modal-content" (click)="$event.stopPropagation()">
          <div class="modal-header">
            <h3>Edit User: {{ selectedUser?.username }}</h3>
            <button class="modal-close" (click)="closeModal()">✕</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Full Name</label>
              <input
                type="text"
                [(ngModel)]="editForm.full_name"
                placeholder="Enter full name"
                class="form-input"
              />
            </div>
            <div class="form-group">
              <label>Role</label>
              <select [(ngModel)]="editForm.role" class="form-input">
                <option value="operations">Operations</option>
                <option value="nurse">Nurse</option>
                <option value="admin">Administrator</option>
              </select>
            </div>
            <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" (click)="closeModal()">Cancel</button>
            <button class="btn-primary" (click)="updateUser()" [disabled]="isLoading">
              {{ isLoading ? 'Updating...' : 'Update User' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Reset Password Modal -->
      <div class="modal" *ngIf="showModal && modalMode === 'reset-password'" (click)="closeModal()">
        <div class="modal-content" (click)="$event.stopPropagation()">
          <div class="modal-header">
            <h3>Reset Password: {{ selectedUser?.username }}</h3>
            <button class="modal-close" (click)="closeModal()">✕</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>New Password *</label>
              <input
                type="password"
                [(ngModel)]="resetPasswordForm.new_password"
                placeholder="Minimum 8 characters"
                class="form-input"
              />
            </div>
            <div class="info-message">
              User will be required to change this password on next login.
            </div>
            <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" (click)="closeModal()">Cancel</button>
            <button class="btn-primary" (click)="resetPassword()" [disabled]="isLoading">
              {{ isLoading ? 'Resetting...' : 'Reset Password' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Delete User Modal -->
      <div class="modal" *ngIf="showModal && modalMode === 'delete'" (click)="closeModal()">
        <div class="modal-content" (click)="$event.stopPropagation()">
          <div class="modal-header">
            <h3>Delete User</h3>
            <button class="modal-close" (click)="closeModal()">✕</button>
          </div>
          <div class="modal-body">
            <p class="warning-text">
              Are you sure you want to delete user <strong>{{ selectedUser?.username }}</strong>?
            </p>
            <p class="warning-text">This action cannot be undone.</p>
            <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" (click)="closeModal()">Cancel</button>
            <button class="btn-danger" (click)="deleteUser()" [disabled]="isLoading">
              {{ isLoading ? 'Deleting...' : 'Delete User' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .user-management-container {
        min-height: 100vh;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
      }

      .page-header {
        background: white;
        border-radius: 12px;
        padding: 1.5rem 2rem;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      }

      .header-content {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }

      .page-header h1 {
        margin: 0;
        color: #2d3748;
        font-size: 1.75rem;
      }

      .header-actions {
        display: flex;
        gap: 1rem;
      }

      .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 1.5rem;
        margin-bottom: 2rem;
      }

      .stat-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        display: flex;
        align-items: center;
        gap: 1rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s;
      }

      .stat-card:hover {
        transform: translateY(-4px);
      }

      .stat-icon {
        font-size: 2.5rem;
        width: 60px;
        height: 60px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 12px;
      }

      .stat-icon.admin {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      }

      .stat-icon.nurse {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      }

      .stat-icon.ops {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
      }

      .stat-icon.total {
        background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
      }

      .stat-content {
        flex: 1;
      }

      .stat-value {
        font-size: 2rem;
        font-weight: bold;
        color: #2d3748;
      }

      .stat-label {
        color: #718096;
        font-size: 0.875rem;
        margin-top: 0.25rem;
      }

      .users-section {
        background: white;
        border-radius: 12px;
        padding: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      }

      .users-section h2 {
        margin: 0 0 1.5rem 0;
        color: #2d3748;
      }

      .table-container {
        overflow-x: auto;
      }

      .users-table {
        width: 100%;
        border-collapse: collapse;
      }

      .users-table th {
        background: #f7fafc;
        padding: 1rem;
        text-align: left;
        font-weight: 600;
        color: #4a5568;
        border-bottom: 2px solid #e2e8f0;
      }

      .users-table td {
        padding: 1rem;
        border-bottom: 1px solid #e2e8f0;
      }

      .users-table tr:hover {
        background: #f7fafc;
      }

      .users-table tr.highlight {
        background: #edf2f7;
      }

      .role-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.875rem;
        font-weight: 500;
      }

      .role-badge.admin {
        background: #e9d8fd;
        color: #553c9a;
      }

      .role-badge.nurse {
        background: #fed7e2;
        color: #97266d;
      }

      .role-badge.operations {
        background: #bee3f8;
        color: #2c5282;
      }

      .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.875rem;
        font-weight: 500;
      }

      .status-badge.success {
        background: #c6f6d5;
        color: #22543d;
      }

      .status-badge.warning {
        background: #feebc8;
        color: #7c2d12;
      }

      .badge-current {
        display: inline-block;
        margin-left: 0.5rem;
        padding: 0.125rem 0.5rem;
        background: #4299e1;
        color: white;
        border-radius: 8px;
        font-size: 0.75rem;
      }

      .action-buttons {
        display: flex;
        gap: 0.5rem;
      }

      .btn-action {
        padding: 0.5rem;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 1rem;
        transition: all 0.2s;
      }

      .btn-action:hover:not(:disabled) {
        transform: scale(1.1);
      }

      .btn-action:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }

      .btn-edit {
        background: #bee3f8;
      }

      .btn-reset {
        background: #feebc8;
      }

      .btn-onboard {
        background: #c6f6d5;
      }

      .btn-delete {
        background: #fed7d7;
      }

      .btn-primary,
      .btn-secondary,
      .btn-logout,
      .btn-danger {
        padding: 0.625rem 1.25rem;
        border: none;
        border-radius: 8px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
      }

      .btn-primary {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
      }

      .btn-primary:hover:not(:disabled) {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
      }

      .btn-secondary {
        background: #e2e8f0;
        color: #2d3748;
      }

      .btn-secondary:hover {
        background: #cbd5e0;
      }

      .btn-logout {
        background: #fc8181;
        color: white;
      }

      .btn-logout:hover {
        background: #f56565;
      }

      .btn-danger {
        background: #fc8181;
        color: white;
      }

      .btn-danger:hover:not(:disabled) {
        background: #f56565;
      }

      .btn-primary:disabled,
      .btn-danger:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .icon {
        margin-right: 0.5rem;
      }

      .modal {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
      }

      .modal-content {
        background: white;
        border-radius: 12px;
        width: 90%;
        max-width: 500px;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
      }

      .modal-header {
        padding: 1.5rem;
        border-bottom: 1px solid #e2e8f0;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }

      .modal-header h3 {
        margin: 0;
        color: #2d3748;
      }

      .modal-close {
        background: none;
        border: none;
        font-size: 1.5rem;
        cursor: pointer;
        color: #718096;
        padding: 0;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 6px;
      }

      .modal-close:hover {
        background: #f7fafc;
      }

      .modal-body {
        padding: 1.5rem;
      }

      .modal-footer {
        padding: 1.5rem;
        border-top: 1px solid #e2e8f0;
        display: flex;
        justify-content: flex-end;
        gap: 1rem;
      }

      .form-group {
        margin-bottom: 1.25rem;
      }

      .form-group label {
        display: block;
        margin-bottom: 0.5rem;
        color: #4a5568;
        font-weight: 500;
      }

      .form-input {
        width: 100%;
        padding: 0.625rem;
        border: 1px solid #cbd5e0;
        border-radius: 6px;
        font-size: 1rem;
      }

      .form-input:focus {
        outline: none;
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
      }

      .error-message {
        background: #fed7d7;
        color: #c53030;
        padding: 0.75rem;
        border-radius: 6px;
        margin-top: 1rem;
      }

      .info-message {
        background: #bee3f8;
        color: #2c5282;
        padding: 0.75rem;
        border-radius: 6px;
        margin-top: 1rem;
      }

      .warning-text {
        color: #c53030;
        margin: 0.5rem 0;
      }
    `,
  ],
})
export class UserManagementPage implements OnInit {
  users: AuthUser[] = [];
  currentUsername = '';
  showModal = false;
  modalMode: 'create' | 'edit' | 'reset-password' | 'delete' = 'create';
  selectedUser: AuthUser | null = null;
  isLoading = false;
  errorMessage = '';

  createForm: UserCreateRequest = {
    username: '',
    password: '',
    role: 'operations',
    full_name: null,
  };

  editForm: UserUpdateRequest = {
    full_name: null,
    role: null,
  };

  resetPasswordForm: AdminResetPasswordRequest = {
    username: '',
    new_password: '',
  };

  constructor(
    private readonly api: ApiService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    const user = this.api.currentUser();
    if (!user) {
      this.router.navigate(['/']);
      return;
    }
    this.currentUsername = user.username;
    this.loadUsers();
  }

  get adminCount(): number {
    return this.users.filter((u) => u.role === 'admin').length;
  }

  get nurseCount(): number {
    return this.users.filter((u) => u.role === 'nurse').length;
  }

  get opsCount(): number {
    return this.users.filter((u) => u.role === 'operations').length;
  }

  get totalUsers(): number {
    return this.users.length;
  }

  getRoleDisplay(role: string): string {
    const map: Record<string, string> = {
      admin: 'Administrator',
      nurse: 'Nurse',
      operations: 'Operations',
    };
    return map[role] || role;
  }

  loadUsers(): void {
    this.api.listUsers().subscribe({
      next: (response) => {
        this.users = response.users;
      },
      error: (err) => {
        console.error('Failed to load users:', err);
      },
    });
  }

  refreshData(): void {
    this.loadUsers();
  }

  showCreateModal(): void {
    this.modalMode = 'create';
    this.createForm = {
      username: '',
      password: '',
      role: 'operations',
      full_name: null,
    };
    this.errorMessage = '';
    this.showModal = true;
  }

  showEditModal(user: AuthUser): void {
    this.modalMode = 'edit';
    this.selectedUser = user;
    this.editForm = {
      full_name: user.full_name,
      role: user.role,
    };
    this.errorMessage = '';
    this.showModal = true;
  }

  showResetPasswordModal(user: AuthUser): void {
    this.modalMode = 'reset-password';
    this.selectedUser = user;
    this.resetPasswordForm = {
      username: user.username,
      new_password: '',
    };
    this.errorMessage = '';
    this.showModal = true;
  }

  showDeleteModal(user: AuthUser): void {
    this.modalMode = 'delete';
    this.selectedUser = user;
    this.errorMessage = '';
    this.showModal = true;
  }

  closeModal(): void {
    this.showModal = false;
    this.selectedUser = null;
    this.errorMessage = '';
  }

  createUser(): void {
    if (!this.createForm.username || !this.createForm.password) {
      this.errorMessage = 'Username and password are required.';
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';
    this.api.createUser(this.createForm).subscribe({
      next: () => {
        this.isLoading = false;
        this.closeModal();
        this.loadUsers();
      },
      error: (err) => {
        this.isLoading = false;
        this.errorMessage = err.error?.detail || 'Failed to create user.';
      },
    });
  }

  updateUser(): void {
    if (!this.selectedUser) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.api.updateUser(this.selectedUser.username, this.editForm).subscribe({
      next: () => {
        this.isLoading = false;
        this.closeModal();
        this.loadUsers();
      },
      error: (err) => {
        this.isLoading = false;
        this.errorMessage = err.error?.detail || 'Failed to update user.';
      },
    });
  }

  resetPassword(): void {
    if (!this.selectedUser || !this.resetPasswordForm.new_password) {
      this.errorMessage = 'New password is required.';
      return;
    }
    this.isLoading = true;
    this.errorMessage = '';
    this.api.adminResetPassword(this.selectedUser.username, this.resetPasswordForm).subscribe({
      next: () => {
        this.isLoading = false;
        this.closeModal();
        this.loadUsers();
      },
      error: (err) => {
        this.isLoading = false;
        this.errorMessage = err.error?.detail || 'Failed to reset password.';
      },
    });
  }

  deleteUser(): void {
    if (!this.selectedUser) return;
    this.isLoading = true;
    this.errorMessage = '';
    this.api.deleteUser(this.selectedUser.username).subscribe({
      next: () => {
        this.isLoading = false;
        this.closeModal();
        this.loadUsers();
      },
      error: (err) => {
        this.isLoading = false;
        this.errorMessage = err.error?.detail || 'Failed to delete user.';
      },
    });
  }

  resetOnboarding(user: AuthUser): void {
    if (!user.onboarding_completed) return;
    this.api.resetOnboarding({ username: user.username }).subscribe({
      next: () => {
        this.loadUsers();
      },
      error: (err) => {
        console.error('Failed to reset onboarding:', err);
      },
    });
  }

  logout(): void {
    this.api.logout();
    this.router.navigate(['/']);
  }
}
