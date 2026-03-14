<?php

namespace Tests\Feature;

use App\Filament\Pages\AuditLogViewer;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class AuditLogViewerTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub that returns realistic audit log data for all API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getAuditLogs(array $filters = [], int $page = 1, int $perPage = 50): array
            {
                $items = [
                    [
                        'id' => 1,
                        'timestamp' => '2026-03-14T10:30:00+00:00',
                        'actor' => 'admin@sanaa.co',
                        'action' => 'GET /api/skills',
                        'resource' => 'http://127.0.0.1:8101/api/skills',
                        'ip_address' => '192.168.1.100',
                        'user_agent' => 'Mozilla/5.0 (Macintosh)',
                        'elapsed_ms' => 45,
                        'success' => true,
                        'error' => null,
                        'details' => ['ip' => '192.168.1.100', 'user_agent' => 'Mozilla/5.0 (Macintosh)', 'elapsed_ms' => 45],
                    ],
                    [
                        'id' => 2,
                        'timestamp' => '2026-03-14T10:29:00+00:00',
                        'actor' => 'admin@sanaa.co',
                        'action' => 'POST /api/command',
                        'resource' => 'http://127.0.0.1:8101/api/command',
                        'ip_address' => '192.168.1.100',
                        'user_agent' => 'Mozilla/5.0 (Macintosh)',
                        'elapsed_ms' => 1200,
                        'success' => true,
                        'error' => null,
                        'details' => ['ip' => '192.168.1.100', 'user_agent' => 'Mozilla/5.0 (Macintosh)', 'elapsed_ms' => 1200],
                    ],
                    [
                        'id' => 3,
                        'timestamp' => '2026-03-14T10:28:00+00:00',
                        'actor' => 'anon:10.0.0.5',
                        'action' => 'GET /api/status',
                        'resource' => 'http://127.0.0.1:8101/api/status',
                        'ip_address' => '10.0.0.5',
                        'user_agent' => 'curl/7.81.0',
                        'elapsed_ms' => 12,
                        'success' => false,
                        'error' => 'HTTP 401',
                        'details' => ['ip' => '10.0.0.5', 'user_agent' => 'curl/7.81.0', 'elapsed_ms' => 12, 'error' => 'HTTP 401'],
                    ],
                ];

                return [
                    'items' => $items,
                    'total' => 3,
                    'page' => $page,
                    'per_page' => $perPage,
                    'pages' => 1,
                ];
            }

            public function getAuditLogEntry(int $id): array
            {
                return [
                    'id' => $id,
                    'timestamp' => '2026-03-14T10:30:00+00:00',
                    'actor' => 'admin@sanaa.co',
                    'action' => 'GET /api/skills',
                    'resource' => 'http://127.0.0.1:8101/api/skills',
                    'ip_address' => '192.168.1.100',
                    'user_agent' => 'Mozilla/5.0 (Macintosh)',
                    'elapsed_ms' => 45,
                    'success' => true,
                    'error' => null,
                    'details' => ['ip' => '192.168.1.100', 'user_agent' => 'Mozilla/5.0 (Macintosh)', 'elapsed_ms' => 45],
                ];
            }
        });
    }

    public function test_page_loads(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->assertSuccessful();
    }

    public function test_displays_audit_entries(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->assertSee('admin@sanaa.co')
            ->assertSee('/api/skills')
            ->assertSee('/api/command')
            ->assertSee('192.168.1.100');
    }

    public function test_displays_methods(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->assertSee('GET')
            ->assertSee('POST');
    }

    public function test_displays_status_badges(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->assertSee('Success')
            ->assertSee('Failed');
    }

    public function test_filter_by_action(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->set('filterAction', 'GET')
            ->call('applyFilters')
            ->assertHasNoErrors();
    }

    public function test_filter_by_date_range(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->set('filterDateFrom', '2026-03-14T00:00')
            ->set('filterDateTo', '2026-03-14T23:59')
            ->call('applyFilters')
            ->assertHasNoErrors();
    }

    public function test_filter_by_actor(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->set('filterActor', 'admin')
            ->call('applyFilters')
            ->assertHasNoErrors();
    }

    public function test_clear_filters(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->set('filterAction', 'POST')
            ->call('clearFilters')
            ->assertSet('filterAction', '')
            ->assertSet('filterActor', '')
            ->assertSet('filterPath', '')
            ->assertSet('currentPage', 1);
    }

    public function test_view_entry_detail(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->call('viewEntry', 1)
            ->assertSet('selectedEntry.id', 1)
            ->assertSee('Audit Entry #1');
    }

    public function test_close_detail(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->call('viewEntry', 1)
            ->call('closeDetail')
            ->assertSet('selectedEntry', null);
    }

    public function test_pagination_next_previous(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->assertSet('currentPage', 1)
            ->call('nextPage')
            ->assertHasNoErrors();
    }

    public function test_navigation_registered(): void
    {
        $this->assertEquals('System', AuditLogViewer::getNavigationGroup());
        $this->assertEquals('heroicon-o-clipboard-document-list', AuditLogViewer::getNavigationIcon());
    }

    public function test_refresh_data_action(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AuditLogViewer::class)
            ->call('refreshData')
            ->assertHasNoErrors();
    }
}
