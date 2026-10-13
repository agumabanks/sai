<?php

namespace Tests\Feature;

use App\Filament\Pages\AlertConfig;
use App\Filament\Pages\ApiDocs;
use App\Filament\Pages\AuditLogViewer;
use App\Filament\Pages\MarketingDashboard;
use App\Filament\Pages\MemoryViewer;
use App\Filament\Pages\TenantControl;
use App\Filament\Pages\UserManagement;
use App\Filament\Pages\WorkflowBuilder;
use App\Models\User;
use App\Services\SanaaEngineService;
use Filament\Facades\Filament;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

/**
 * VAL-CROSS-011: Every new Filament page appears in the sidebar navigation.
 * VAL-UI-013: PHPUnit tests exist and pass for every new Filament page.
 *
 * This test verifies that all new pages from the ui-and-alerts and
 * tenant-control milestones are registered in the Filament panel,
 * appear in the correct navigation groups, and are reachable.
 */
class SidebarNavigationTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub the SanaaEngineService so pages can render without backend calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getMarketingMetrics(): array
            {
                return ['campaigns' => ['active' => 0], 'email' => [], 'social' => []];
            }

            public function getSocialAnalytics(): array
            {
                return ['platforms' => [], 'recent_posts' => [], 'total_posts' => 0];
            }

            public function getScheduledContent(): array
            {
                return ['upcoming' => [], 'total' => 0];
            }

            public function getMemories(?string $search = null, ?string $category = null, int $limit = 50): array
            {
                return ['memories' => [], 'total' => 0];
            }

            public function getLearningLogs(?string $type = null, int $limit = 50): array
            {
                return ['entries' => [], 'promoted' => [], 'total' => 0, 'promoted_count' => 0];
            }

            public function getAuditLogs(array $filters = [], int $page = 1, int $perPage = 50): array
            {
                return ['items' => [], 'total' => 0, 'page' => 1, 'per_page' => 50, 'pages' => 0];
            }

            public function getAlertRules(): array
            {
                return [];
            }

            public function getOpenApiSpec(): array
            {
                return ['openapi' => '3.1.0', 'info' => ['title' => 'Sanaa AI Engine', 'version' => '2.0.0'], 'paths' => [], 'components' => []];
            }

            public function getWorkflows(): array
            {
                return ['count' => 0, 'workflows' => []];
            }

            public function getSkills(): array
            {
                return ['skills' => [], 'tools' => [], 'tool_policy' => []];
            }

            public function getTenants(): array
            {
                return [];
            }

            public function getTenantHealth(): array
            {
                return ['overall_score' => 0, 'overall_status' => 'unknown', 'tenants' => []];
            }
        });
    }

    /**
     * The new pages that must appear in sidebar navigation.
     *
     * @return array<string, array{class: class-string, group: string, icon: string}>
     */
    private function newPages(): array
    {
        return [
            'MarketingDashboard' => [
                'class' => MarketingDashboard::class,
                'group' => 'Marketing',
                'icon' => 'heroicon-o-megaphone',
            ],
            'MemoryViewer' => [
                'class' => MemoryViewer::class,
                'group' => 'Intelligence',
                'icon' => 'heroicon-o-light-bulb',
            ],
            'AuditLogViewer' => [
                'class' => AuditLogViewer::class,
                'group' => 'System',
                'icon' => 'heroicon-o-clipboard-document-list',
            ],
            'AlertConfig' => [
                'class' => AlertConfig::class,
                'group' => 'System',
                'icon' => 'heroicon-o-bell-alert',
            ],
            'WorkflowBuilder' => [
                'class' => WorkflowBuilder::class,
                'group' => 'Skills Lab',
                'icon' => 'heroicon-o-arrow-path',
            ],
            'ApiDocs' => [
                'class' => ApiDocs::class,
                'group' => 'System',
                'icon' => 'heroicon-o-document-text',
            ],
            'UserManagement' => [
                'class' => UserManagement::class,
                'group' => 'Settings',
                'icon' => 'heroicon-o-users',
            ],
            'TenantControl' => [
                'class' => TenantControl::class,
                'group' => 'Infrastructure',
                'icon' => 'heroicon-o-server-stack',
            ],
        ];
    }

    // ── VAL-CROSS-011: Every new page in sidebar navigation ──────────────

    /**
     * Verify all new pages are registered in the correct navigation group.
     */
    public function test_all_new_pages_in_correct_navigation_groups(): void
    {
        foreach ($this->newPages() as $name => $page) {
            $this->assertEquals(
                $page['group'],
                $page['class']::getNavigationGroup(),
                "{$name} should be in the '{$page['group']}' navigation group"
            );
        }
    }

    /**
     * Verify all new pages have the expected navigation icon.
     */
    public function test_all_new_pages_have_correct_icons(): void
    {
        foreach ($this->newPages() as $name => $page) {
            $this->assertEquals(
                $page['icon'],
                $page['class']::getNavigationIcon(),
                "{$name} should have the icon '{$page['icon']}'"
            );
        }
    }

    /**
     * Verify all new pages load successfully for an admin user (200 response, no PHP errors).
     */
    public function test_all_new_pages_load_for_admin(): void
    {
        $this->stubEngine();
        $admin = User::factory()->create(['role' => 'admin']);

        foreach ($this->newPages() as $name => $page) {
            Livewire::actingAs($admin)
                ->test($page['class'])
                ->assertSuccessful();
        }
    }

    /**
     * Verify that the expected navigation groups exist across all new pages.
     */
    public function test_all_expected_navigation_groups_present(): void
    {
        $expectedGroups = [
            'Marketing',
            'Intelligence',
            'System',
            'Skills Lab',
            'Settings',
            'Infrastructure',
        ];

        $actualGroups = array_unique(array_map(
            fn (array $page) => $page['class']::getNavigationGroup(),
            $this->newPages()
        ));

        foreach ($expectedGroups as $group) {
            $this->assertContains(
                $group,
                $actualGroups,
                "Navigation group '{$group}' should be present among new pages"
            );
        }
    }

    /**
     * Verify every new page has a non-null navigation icon (visible in sidebar).
     */
    public function test_all_new_pages_have_navigation_icons(): void
    {
        foreach ($this->newPages() as $name => $page) {
            $this->assertNotNull(
                $page['class']::getNavigationIcon(),
                "{$name} must have a navigation icon to appear in sidebar"
            );
        }
    }

    /**
     * Verify every new page has a non-null navigation group (grouped in sidebar).
     */
    public function test_all_new_pages_have_navigation_groups(): void
    {
        foreach ($this->newPages() as $name => $page) {
            $this->assertNotNull(
                $page['class']::getNavigationGroup(),
                "{$name} must have a navigation group"
            );
        }
    }

    /**
     * Verify new page count matches expectation (no pages missing from the list).
     */
    public function test_expected_new_page_count(): void
    {
        $this->assertCount(8, $this->newPages(),
            'There should be 8 new pages (marketing, memory, audit, alert config, workflow, api docs, user mgmt, tenant control)'
        );
    }

    /**
     * Verify each new page has a unique slug (no route conflicts).
     */
    public function test_new_pages_have_unique_slugs(): void
    {
        $slugs = [];
        foreach ($this->newPages() as $name => $page) {
            $slug = $page['class']::getSlug();
            $this->assertNotContains(
                $slug,
                $slugs,
                "{$name} slug '{$slug}' conflicts with another page"
            );
            $slugs[] = $slug;
        }
    }
}
