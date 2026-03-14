<?php

namespace Tests\Feature;

use App\Filament\Pages\MemoryViewer;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class MemoryViewerTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub that returns realistic memory and learning log data for all API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getMemories(?string $search = null, ?string $category = null, int $limit = 50): array
            {
                $memories = [
                    [
                        'id' => 1,
                        'content' => 'The server finance.sanaa.ug runs on port 443 with Nginx reverse proxy',
                        'category' => 'fact',
                        'confidence' => 0.9,
                        'source' => 'watchdog',
                        'verified' => true,
                        'created_at' => '2026-03-14T10:00:00+00:00',
                        'updated_at' => '2026-03-14T10:00:00+00:00',
                        'access_count' => 5,
                        'last_accessed_at' => '2026-03-14T12:00:00+00:00',
                    ],
                    [
                        'id' => 2,
                        'content' => 'User prefers concise responses without verbose explanations',
                        'category' => 'preference',
                        'confidence' => 0.7,
                        'source' => 'conversation',
                        'verified' => false,
                        'created_at' => '2026-03-13T08:00:00+00:00',
                        'updated_at' => '2026-03-13T08:00:00+00:00',
                        'access_count' => 2,
                        'last_accessed_at' => '2026-03-14T09:00:00+00:00',
                    ],
                    [
                        'id' => 3,
                        'content' => 'To restart Celery worker: sudo systemctl restart antigravity-worker',
                        'category' => 'procedure',
                        'confidence' => 0.85,
                        'source' => 'reflection',
                        'verified' => false,
                        'created_at' => '2026-03-12T15:00:00+00:00',
                        'updated_at' => '2026-03-12T15:00:00+00:00',
                        'access_count' => 3,
                        'last_accessed_at' => '2026-03-14T08:00:00+00:00',
                    ],
                ];

                // Filter by category if provided
                if ($category) {
                    $memories = array_values(array_filter($memories, fn ($m) => $m['category'] === $category));
                }

                // Filter by search if provided
                if ($search) {
                    $memories = array_values(array_filter($memories, fn ($m) => stripos($m['content'], $search) !== false));
                }

                return [
                    'memories' => $memories,
                    'total' => count($memories),
                    'search' => $search,
                    'category' => $category,
                ];
            }

            public function getLearningLogs(?string $type = null, int $limit = 50): array
            {
                $entries = [
                    [
                        'id' => 101,
                        'timestamp' => '2026-03-14T07:51:00+00:00',
                        'log_type' => 'LEARNINGS',
                        'source' => 'conversation',
                        'content' => 'The admin prefers dark mode interfaces with minimal clutter',
                        'confidence' => 0.8,
                        'category' => 'ui_preference',
                        'promoted' => true,
                        'promotion_timestamp' => '2026-03-14T09:00:00+00:00',
                    ],
                    [
                        'id' => 102,
                        'timestamp' => '2026-03-14T06:30:00+00:00',
                        'log_type' => 'ERRORS',
                        'source' => 'error',
                        'content' => 'Skill tenant_provisioning had 15 failures in the last 7 days',
                        'confidence' => 0.9,
                        'category' => 'skill_failure',
                        'promoted' => false,
                        'promotion_timestamp' => null,
                    ],
                    [
                        'id' => 103,
                        'timestamp' => '2026-03-13T14:00:00+00:00',
                        'log_type' => 'FEATURE_REQUESTS',
                        'source' => 'user',
                        'content' => 'Add support for WhatsApp Business API integration',
                        'confidence' => 0.6,
                        'category' => 'integration',
                        'promoted' => false,
                        'promotion_timestamp' => null,
                    ],
                ];

                // Filter by type if provided
                if ($type) {
                    $entries = array_values(array_filter($entries, fn ($e) => $e['log_type'] === $type));
                }

                $promoted = array_values(array_filter($entries, fn ($e) => $e['promoted']));

                return [
                    'entries' => $entries,
                    'promoted' => $promoted,
                    'total' => count($entries),
                    'promoted_count' => count($promoted),
                    'log_type' => $type,
                ];
            }
        });
    }

    public function test_page_loads(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->assertSuccessful();
    }

    public function test_displays_memories(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->assertSee('Memory Viewer')
            ->assertSee('finance.sanaa.ug')
            ->assertSee('preference')
            ->assertSee('procedure');
    }

    public function test_displays_learning_logs(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->call('switchTab', 'learning-logs')
            ->assertSee('Learning Logs')
            ->assertSee('dark mode interfaces')
            ->assertSee('tenant_provisioning')
            ->assertSee('WhatsApp Business');
    }

    public function test_displays_promoted_learnings(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->call('switchTab', 'promoted')
            ->assertSee('Promoted Learnings')
            ->assertSee('dark mode interfaces');
    }

    public function test_search_memories(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->set('searchQuery', 'finance')
            ->assertSee('finance.sanaa.ug')
            ->assertDontSee('User prefers concise');
    }

    public function test_filter_by_category(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->set('categoryFilter', 'fact')
            ->assertSee('finance.sanaa.ug')
            ->assertDontSee('User prefers concise');
    }

    public function test_filter_learning_logs_by_type(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->call('switchTab', 'learning-logs')
            ->set('logTypeFilter', 'ERRORS')
            ->assertSee('tenant_provisioning')
            ->assertDontSee('WhatsApp Business');
    }

    public function test_navigation_registered(): void
    {
        $this->assertEquals('Intelligence', MemoryViewer::getNavigationGroup());
        $this->assertEquals('heroicon-o-light-bulb', MemoryViewer::getNavigationIcon());
    }

    public function test_refresh_data_action(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->call('refreshData')
            ->assertHasNoErrors();
    }

    public function test_tab_switching(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MemoryViewer::class)
            ->assertSet('activeTab', 'memories')
            ->call('switchTab', 'learning-logs')
            ->assertSet('activeTab', 'learning-logs')
            ->call('switchTab', 'promoted')
            ->assertSet('activeTab', 'promoted')
            ->call('switchTab', 'memories')
            ->assertSet('activeTab', 'memories');
    }
}
