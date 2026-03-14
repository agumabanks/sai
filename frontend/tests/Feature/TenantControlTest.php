<?php

namespace Tests\Feature;

use App\Filament\Pages\TenantControl;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class TenantControlTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub that returns realistic tenant data for all API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getTenants(): array
            {
                return [
                    [
                        'id' => 1,
                        'name' => 'finance.sanaa.ug',
                        'type' => 'finance',
                        'url' => 'https://finance.sanaa.ug',
                        'status' => 'active',
                        'health_score' => 95.0,
                        'last_checked' => '2026-03-14T10:00:00',
                        'config' => [],
                    ],
                    [
                        'id' => 2,
                        'name' => 'soko',
                        'type' => 'ecommerce',
                        'url' => 'https://soko.sanaa.ug',
                        'status' => 'degraded',
                        'health_score' => 60.0,
                        'last_checked' => '2026-03-14T09:55:00',
                        'config' => [],
                    ],
                    [
                        'id' => 3,
                        'name' => 'mailcow',
                        'type' => 'email',
                        'url' => 'https://mail.sanaa.ug',
                        'status' => 'active',
                        'health_score' => 88.0,
                        'last_checked' => '2026-03-14T09:50:00',
                        'config' => [],
                    ],
                    [
                        'id' => 4,
                        'name' => 'kalamba.sanaa.ug',
                        'type' => 'finance',
                        'url' => 'https://kalamba.sanaa.ug',
                        'status' => 'down',
                        'health_score' => 0.0,
                        'last_checked' => '2026-03-14T09:45:00',
                        'config' => [],
                    ],
                ];
            }

            public function getTenantHealth(): array
            {
                return [
                    'overall_score' => 72.5,
                    'overall_status' => 'degraded',
                    'tenants' => $this->getTenants(),
                    'checked_at' => '2026-03-14T10:00:00',
                ];
            }

            public function enableTenant(int $id): array
            {
                return ['id' => $id, 'status' => 'active'];
            }

            public function disableTenant(int $id): array
            {
                return ['id' => $id, 'status' => 'inactive'];
            }

            public function checkTenant(int $id): array
            {
                return [
                    'tenant_id' => $id,
                    'status' => 'active',
                    'health_score' => 95.0,
                    'response_time_ms' => 120,
                ];
            }
        });
    }

    public function test_page_loads(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->assertSuccessful();
    }

    public function test_displays_tenant_cards(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->assertSee('finance.sanaa.ug')
            ->assertSee('soko')
            ->assertSee('mailcow')
            ->assertSee('kalamba.sanaa.ug');
    }

    public function test_displays_tenant_types(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->assertSee('Finance')
            ->assertSee('E-Commerce')
            ->assertSee('Email');
    }

    public function test_shows_health_scores(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->assertSee('95')
            ->assertSee('60')
            ->assertSee('88');
    }

    public function test_shows_status_badges(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->assertSee('Active')
            ->assertSee('Degraded')
            ->assertSee('Down');
    }

    public function test_enable_tenant_action(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->call('enableTenant', 4)
            ->assertHasNoErrors();
    }

    public function test_disable_tenant_action(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->call('disableTenant', 1)
            ->assertHasNoErrors();
    }

    public function test_check_tenant_action(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(TenantControl::class)
            ->call('checkTenant', 1)
            ->assertHasNoErrors();
    }

    public function test_navigation_registered(): void
    {
        // Verify the page is registered with the correct navigation group
        $this->assertEquals('Infrastructure', TenantControl::getNavigationGroup());
        $this->assertEquals('heroicon-o-server-stack', TenantControl::getNavigationIcon());
    }
}
