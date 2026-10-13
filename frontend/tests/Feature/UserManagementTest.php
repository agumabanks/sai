<?php

namespace Tests\Feature;

use App\Filament\Pages\UserManagement;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class UserManagementTest extends TestCase
{
    use RefreshDatabase;

    public function test_page_loads_for_admin(): void
    {
        $user = User::factory()->create(['role' => 'admin']);

        Livewire::actingAs($user)
            ->test(UserManagement::class)
            ->assertSuccessful();
    }

    public function test_page_displays_users_table(): void
    {
        $admin = User::factory()->create(['role' => 'admin', 'name' => 'Admin User']);
        $operator = User::factory()->create(['role' => 'operator', 'name' => 'Operator User']);
        $viewer = User::factory()->create(['role' => 'viewer', 'name' => 'Viewer User']);

        Livewire::actingAs($admin)
            ->test(UserManagement::class)
            ->assertSee('Admin User')
            ->assertSee('Operator User')
            ->assertSee('Viewer User');
    }

    public function test_admin_can_create_user(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        Livewire::actingAs($admin)
            ->test(UserManagement::class)
            ->call('createUser', [
                'name' => 'New Test User',
                'email' => 'newuser@test.com',
                'password' => 'securepassword123',
                'role' => 'operator',
            ])
            ->assertHasNoErrors();

        $this->assertDatabaseHas('users', [
            'email' => 'newuser@test.com',
            'role' => 'operator',
        ]);
    }

    public function test_admin_can_edit_user_role(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $target = User::factory()->create(['role' => 'viewer']);

        Livewire::actingAs($admin)
            ->test(UserManagement::class)
            ->call('updateUser', $target->id, [
                'name' => $target->name,
                'email' => $target->email,
                'role' => 'operator',
            ])
            ->assertHasNoErrors();

        $this->assertDatabaseHas('users', [
            'id' => $target->id,
            'role' => 'operator',
        ]);
    }

    public function test_admin_can_soft_delete_user(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $target = User::factory()->create(['role' => 'viewer']);

        Livewire::actingAs($admin)
            ->test(UserManagement::class)
            ->call('deleteUser', $target->id)
            ->assertHasNoErrors();

        $this->assertSoftDeleted('users', ['id' => $target->id]);
    }

    public function test_operator_cannot_access_page(): void
    {
        $operator = User::factory()->create(['role' => 'operator']);

        Livewire::actingAs($operator)
            ->test(UserManagement::class)
            ->assertForbidden();
    }

    public function test_viewer_cannot_access_page(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);

        Livewire::actingAs($viewer)
            ->test(UserManagement::class)
            ->assertForbidden();
    }

    public function test_navigation_registered(): void
    {
        $this->assertEquals('Settings', UserManagement::getNavigationGroup());
        $this->assertEquals('heroicon-o-users', UserManagement::getNavigationIcon());
    }

    public function test_user_model_has_role_field(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $this->assertEquals('admin', $user->role);

        $user2 = User::factory()->create(['role' => 'operator']);
        $this->assertEquals('operator', $user2->role);

        $user3 = User::factory()->create(['role' => 'viewer']);
        $this->assertEquals('viewer', $user3->role);
    }

    public function test_user_role_helper_methods(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $operator = User::factory()->create(['role' => 'operator']);
        $viewer = User::factory()->create(['role' => 'viewer']);

        $this->assertTrue($admin->isAdmin());
        $this->assertFalse($admin->isOperator());
        $this->assertFalse($admin->isViewer());

        $this->assertFalse($operator->isAdmin());
        $this->assertTrue($operator->isOperator());
        $this->assertFalse($operator->isViewer());

        $this->assertFalse($viewer->isAdmin());
        $this->assertFalse($viewer->isOperator());
        $this->assertTrue($viewer->isViewer());
    }

    public function test_create_user_with_duplicate_email_fails(): void
    {
        $admin = User::factory()->create(['role' => 'admin', 'email' => 'existing@test.com']);

        Livewire::actingAs($admin)
            ->test(UserManagement::class)
            ->call('createUser', [
                'name' => 'Duplicate User',
                'email' => 'existing@test.com',
                'password' => 'password123',
                'role' => 'viewer',
            ])
            ->assertHasNoErrors();

        // Should still only have one user with that email (the admin)
        $this->assertEquals(1, User::where('email', 'existing@test.com')->count());
    }
}
