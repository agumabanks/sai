<?php

namespace Tests\Feature;

use App\Filament\Pages\AiBrainSettings;
use App\Filament\Pages\AuditLogViewer;
use App\Filament\Pages\Dashboard;
use App\Filament\Pages\MarketingDashboard;
use App\Filament\Pages\MemoryViewer;
use App\Filament\Pages\SessionPolicy;
use App\Filament\Pages\UserManagement;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class RbacTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub out the engine to avoid real API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getStatus(): array
            {
                return ['server' => ['cpu' => ['percent' => 10, 'status' => 'ok', 'cores' => 4, 'load_1m' => 1], 'memory' => ['percent' => 50, 'status' => 'ok', 'total_gb' => 16], 'disk' => ['percent' => 40, 'free_gb' => 100, 'status' => 'ok'], 'uptime_since' => '2026-03-10T00:00:00', 'services' => [], 'overall_status' => 'ok'], 'alerts' => ['unacknowledged' => 0], 'channels' => ['active_provider' => 'groq']];
            }

            public function getBrainConfig(): array
            {
                return ['provider' => 'auto'];
            }

            public function getToolPolicy(): array
            {
                return ['policy' => ['enabled' => true, 'mode' => 'allowlist']];
            }

            public function getSkills(): array
            {
                return ['skills' => [], 'tools' => [], 'tool_policy' => []];
            }

            public function getSessionPolicy(): array
            {
                return ['policy' => []];
            }

            public function getSessions(int $limit = 100): array
            {
                return ['sessions' => []];
            }

            public function getDoctorReport(): array
            {
                return [];
            }

            public function getWorkflowRuns(int $limit = 50): array
            {
                return [];
            }

            public function getStrategicSignals(int $limit = 10): array
            {
                return [];
            }

            public function getSystemWisdom(): array
            {
                return [];
            }

            public function getMarketingMetrics(): array
            {
                return ['campaigns' => [], 'email' => [], 'social' => []];
            }

            public function getSocialAnalytics(): array
            {
                return ['platforms' => [], 'recent_posts' => []];
            }

            public function getScheduledContent(): array
            {
                return ['upcoming' => []];
            }

            public function getMemories(?string $search = null, ?string $category = null, int $limit = 50): array
            {
                return [];
            }

            public function getLearningLogs(?string $type = null, int $limit = 50): array
            {
                return [];
            }

            public function getTenants(): array
            {
                return [];
            }

            public function getTenantHealth(): array
            {
                return ['overall_score' => 0, 'overall_status' => 'unknown', 'tenants' => []];
            }

            public function getAuditLogs(array $filters = [], int $page = 1, int $perPage = 50): array
            {
                return ['items' => [], 'total' => 0, 'page' => 1, 'per_page' => 50, 'pages' => 0];
            }

            public function getAlerts(int $limit = 10): array
            {
                return [];
            }

            public function getActivities(int $limit = 20): array
            {
                return [];
            }

            public function getBriefings(int $limit = 20): array
            {
                return [];
            }

            public function getLatestSignal(): array
            {
                return ['status' => 'none'];
            }

            public function getWatchdogAdvisor(): array
            {
                return [];
            }

            public function getLatestBriefingQa(): array
            {
                return [];
            }
        });
    }

    // ── Admin can access ALL pages ──────────────────────────────────────

    public function test_admin_can_access_dashboard(): void
    {
        $this->stubEngine();
        $admin = User::factory()->create(['role' => 'admin']);

        Livewire::actingAs($admin)
            ->test(Dashboard::class)
            ->assertSuccessful();
    }

    public function test_admin_can_access_settings_pages(): void
    {
        $this->stubEngine();
        $admin = User::factory()->create(['role' => 'admin']);

        Livewire::actingAs($admin)
            ->test(AiBrainSettings::class)
            ->assertSuccessful();

        Livewire::actingAs($admin)
            ->test(SessionPolicy::class)
            ->assertSuccessful();

        Livewire::actingAs($admin)
            ->test(UserManagement::class)
            ->assertSuccessful();
    }

    public function test_admin_can_access_system_pages(): void
    {
        $this->stubEngine();
        $admin = User::factory()->create(['role' => 'admin']);

        Livewire::actingAs($admin)
            ->test(AuditLogViewer::class)
            ->assertSuccessful();
    }

    // ── Operator CANNOT access Settings or User Management ──────────────

    public function test_operator_cannot_access_brain_settings(): void
    {
        $this->stubEngine();
        $operator = User::factory()->create(['role' => 'operator']);

        Livewire::actingAs($operator)
            ->test(AiBrainSettings::class)
            ->assertForbidden();
    }

    public function test_operator_cannot_access_session_policy(): void
    {
        $this->stubEngine();
        $operator = User::factory()->create(['role' => 'operator']);

        Livewire::actingAs($operator)
            ->test(SessionPolicy::class)
            ->assertForbidden();
    }

    public function test_operator_cannot_access_user_management(): void
    {
        $this->stubEngine();
        $operator = User::factory()->create(['role' => 'operator']);

        Livewire::actingAs($operator)
            ->test(UserManagement::class)
            ->assertForbidden();
    }

    public function test_operator_can_access_dashboard(): void
    {
        $this->stubEngine();
        $operator = User::factory()->create(['role' => 'operator']);

        Livewire::actingAs($operator)
            ->test(Dashboard::class)
            ->assertSuccessful();
    }

    public function test_operator_can_access_non_settings_pages(): void
    {
        $this->stubEngine();
        $operator = User::factory()->create(['role' => 'operator']);

        Livewire::actingAs($operator)
            ->test(AuditLogViewer::class)
            ->assertSuccessful();

        Livewire::actingAs($operator)
            ->test(MarketingDashboard::class)
            ->assertSuccessful();

        Livewire::actingAs($operator)
            ->test(MemoryViewer::class)
            ->assertSuccessful();
    }

    // ── Viewer can access pages but read-only (no action buttons) ───────

    public function test_viewer_can_access_dashboard(): void
    {
        $this->stubEngine();
        $viewer = User::factory()->create(['role' => 'viewer']);

        Livewire::actingAs($viewer)
            ->test(Dashboard::class)
            ->assertSuccessful();
    }

    public function test_viewer_cannot_access_settings_pages(): void
    {
        $this->stubEngine();
        $viewer = User::factory()->create(['role' => 'viewer']);

        Livewire::actingAs($viewer)
            ->test(AiBrainSettings::class)
            ->assertForbidden();

        Livewire::actingAs($viewer)
            ->test(SessionPolicy::class)
            ->assertForbidden();

        Livewire::actingAs($viewer)
            ->test(UserManagement::class)
            ->assertForbidden();
    }

    public function test_viewer_can_access_read_only_pages(): void
    {
        $this->stubEngine();
        $viewer = User::factory()->create(['role' => 'viewer']);

        Livewire::actingAs($viewer)
            ->test(AuditLogViewer::class)
            ->assertSuccessful();

        Livewire::actingAs($viewer)
            ->test(MarketingDashboard::class)
            ->assertSuccessful();

        Livewire::actingAs($viewer)
            ->test(MemoryViewer::class)
            ->assertSuccessful();
    }

    // ── RBAC consistency across pages ───────────────────────────────────

    public function test_rbac_applied_consistently(): void
    {
        $this->stubEngine();
        $operator = User::factory()->create(['role' => 'operator']);

        // Settings group pages: all forbidden for operator
        $settingsPages = [
            AiBrainSettings::class,
            SessionPolicy::class,
            UserManagement::class,
        ];

        foreach ($settingsPages as $pageClass) {
            Livewire::actingAs($operator)
                ->test($pageClass)
                ->assertForbidden();
        }
    }

    public function test_default_role_is_viewer(): void
    {
        $user = User::factory()->create();
        $this->assertEquals('viewer', $user->role);
    }
}
