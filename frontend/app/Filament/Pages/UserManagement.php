<?php

namespace App\Filament\Pages;

use App\Models\User;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Validator;

class UserManagement extends Page
{
    protected static ?string $navigationIcon  = 'heroicon-o-users';
    protected static ?string $navigationGroup = 'Settings';
    protected static ?int $navigationSort     = 3;
    protected static string $view             = 'filament.pages.user-management';

    public array $users          = [];
    public bool $showCreateModal = false;
    public bool $showEditModal   = false;
    public ?int $editingUserId   = null;

    // ── Create form state ───────────────────────────────────────────────
    public string $createName     = '';
    public string $createEmail    = '';
    public string $createPassword = '';
    public string $createRole     = 'viewer';

    // ── Edit form state ─────────────────────────────────────────────────
    public string $editName     = '';
    public string $editEmail    = '';
    public string $editPassword = '';
    public string $editRole     = 'viewer';

    /**
     * Only admins can access this page.
     */
    public static function canAccess(): bool
    {
        $user = auth()->user();

        return $user instanceof User && $user->isAdmin();
    }

    public function mount(): void
    {
        $this->loadUsers();
    }

    public function loadUsers(): void
    {
        $this->users = User::query()
            ->orderBy('created_at', 'desc')
            ->get(['id', 'name', 'email', 'role', 'created_at', 'deleted_at'])
            ->toArray();
    }

    // ── Create ──────────────────────────────────────────────────────────

    public function openCreateModal(): void
    {
        $this->createName     = '';
        $this->createEmail    = '';
        $this->createPassword = '';
        $this->createRole     = 'viewer';
        $this->showCreateModal = true;
    }

    public function closeCreateModal(): void
    {
        $this->showCreateModal = false;
    }

    public function createUser(?array $data = null): void
    {
        $input = $data ?? [
            'name'     => $this->createName,
            'email'    => $this->createEmail,
            'password' => $this->createPassword,
            'role'     => $this->createRole,
        ];

        $validator = Validator::make($input, [
            'name'     => 'required|string|max:255',
            'email'    => 'required|email|unique:users,email',
            'password' => 'required|string|min:8',
            'role'     => 'required|in:admin,operator,viewer',
        ]);

        if ($validator->fails()) {
            Notification::make()
                ->title('Validation failed')
                ->body($validator->errors()->first())
                ->danger()
                ->send();

            return;
        }

        User::create([
            'name'     => $input['name'],
            'email'    => $input['email'],
            'password' => Hash::make($input['password']),
            'role'     => $input['role'],
        ]);

        $this->showCreateModal = false;
        $this->loadUsers();

        Notification::make()
            ->title('User created')
            ->body("User {$input['name']} has been created as {$input['role']}.")
            ->success()
            ->send();
    }

    // ── Edit ────────────────────────────────────────────────────────────

    public function openEditModal(int $userId): void
    {
        $user = User::withTrashed()->find($userId);

        if (! $user) {
            return;
        }

        $this->editingUserId = $userId;
        $this->editName      = $user->name;
        $this->editEmail     = $user->email;
        $this->editPassword  = '';
        $this->editRole      = $user->role;
        $this->showEditModal = true;
    }

    public function closeEditModal(): void
    {
        $this->showEditModal = false;
        $this->editingUserId = null;
    }

    public function updateUser(?int $userId = null, ?array $data = null): void
    {
        $id = $userId ?? $this->editingUserId;
        $user = User::withTrashed()->find($id);

        if (! $user) {
            Notification::make()->title('User not found')->danger()->send();
            return;
        }

        $input = $data ?? [
            'name'  => $this->editName,
            'email' => $this->editEmail,
            'role'  => $this->editRole,
        ];

        $rules = [
            'name'  => 'required|string|max:255',
            'email' => 'required|email|unique:users,email,' . $user->id,
            'role'  => 'required|in:admin,operator,viewer',
        ];

        $validator = Validator::make($input, $rules);

        if ($validator->fails()) {
            Notification::make()
                ->title('Validation failed')
                ->body($validator->errors()->first())
                ->danger()
                ->send();

            return;
        }

        $user->update([
            'name'  => $input['name'],
            'email' => $input['email'],
            'role'  => $input['role'],
        ]);

        // Optional password update
        $password = $data['password'] ?? ($this->editPassword ?: null);
        if ($password && strlen($password) >= 8) {
            $user->update(['password' => Hash::make($password)]);
        }

        $this->showEditModal = false;
        $this->editingUserId = null;
        $this->loadUsers();

        Notification::make()
            ->title('User updated')
            ->body("User {$input['name']} has been updated.")
            ->success()
            ->send();
    }

    // ── Delete (soft) ───────────────────────────────────────────────────

    public function deleteUser(int $userId): void
    {
        $user = User::find($userId);

        if (! $user) {
            Notification::make()->title('User not found')->danger()->send();
            return;
        }

        // Prevent deleting yourself
        if ($user->id === auth()->id()) {
            Notification::make()
                ->title('Cannot delete yourself')
                ->danger()
                ->send();

            return;
        }

        $user->delete(); // SoftDeletes

        $this->loadUsers();

        Notification::make()
            ->title('User deleted')
            ->body("User {$user->name} has been deactivated.")
            ->success()
            ->send();
    }

    // ── Restore ─────────────────────────────────────────────────────────

    public function restoreUser(int $userId): void
    {
        $user = User::withTrashed()->find($userId);

        if (! $user) {
            Notification::make()->title('User not found')->danger()->send();
            return;
        }

        $user->restore();
        $this->loadUsers();

        Notification::make()
            ->title('User restored')
            ->body("User {$user->name} has been reactivated.")
            ->success()
            ->send();
    }

    // ── View helpers ────────────────────────────────────────────────────

    public function getRoleBadge(string $role): array
    {
        return match ($role) {
            'admin'    => ['label' => 'Admin', 'color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20'],
            'operator' => ['label' => 'Operator', 'color' => 'text-[#5e5ce6] bg-[#5e5ce6]/10 border-[#5e5ce6]/20'],
            'viewer'   => ['label' => 'Viewer', 'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20'],
            default    => ['label' => ucfirst($role), 'color' => 'text-white/50 bg-white/5 border-white/10'],
        };
    }
}
