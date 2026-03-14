<?php

namespace Tests\Feature;

use App\Filament\Pages\MarketingDashboard;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class MarketingDashboardTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub that returns realistic marketing data for all API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getMarketingMetrics(): array
            {
                return [
                    'campaigns' => [
                        'active' => 3,
                        'total' => 12,
                        'draft' => 2,
                        'sent' => 7,
                    ],
                    'email' => [
                        'total_sent' => 1520,
                        'open_rate' => 34.5,
                        'click_rate' => 12.3,
                        'bounce_rate' => 2.1,
                    ],
                    'social' => [
                        'total_posts' => 45,
                        'scheduled' => 8,
                        'published' => 37,
                    ],
                ];
            }

            public function getSocialAnalytics(): array
            {
                return [
                    'total_posts' => 45,
                    'platforms' => [
                        'twitter' => ['scheduled' => 3, 'published' => 15],
                        'linkedin' => ['scheduled' => 2, 'published' => 12],
                        'facebook' => ['scheduled' => 3, 'published' => 10],
                    ],
                    'recent_posts' => [
                        [
                            'platform' => 'twitter',
                            'content' => 'Exciting news about our latest product launch! #innovation',
                            'scheduled_time' => '2026-03-15T10:00:00',
                            'status' => 'scheduled',
                        ],
                        [
                            'platform' => 'linkedin',
                            'content' => 'Proud to announce our Q1 results exceeded expectations.',
                            'scheduled_time' => '2026-03-14T14:00:00',
                            'status' => 'published',
                        ],
                        [
                            'platform' => 'facebook',
                            'content' => 'Join us for an amazing community event this weekend! 🎉',
                            'scheduled_time' => '2026-03-16T09:00:00',
                            'status' => 'scheduled',
                        ],
                    ],
                ];
            }

            public function getScheduledContent(): array
            {
                return [
                    'upcoming' => [
                        [
                            'type' => 'social_post',
                            'title' => 'Product Launch Tweet',
                            'platform' => 'twitter',
                            'scheduled_time' => '2026-03-15T10:00:00',
                            'status' => 'scheduled',
                        ],
                        [
                            'type' => 'email_campaign',
                            'title' => 'March Newsletter',
                            'platform' => 'email',
                            'scheduled_time' => '2026-03-17T08:00:00',
                            'status' => 'draft',
                        ],
                        [
                            'type' => 'social_post',
                            'title' => 'Community Event Announcement',
                            'platform' => 'facebook',
                            'scheduled_time' => '2026-03-16T09:00:00',
                            'status' => 'scheduled',
                        ],
                    ],
                    'total' => 3,
                ];
            }
        });
    }

    public function test_page_loads(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MarketingDashboard::class)
            ->assertSuccessful();
    }

    public function test_displays_campaign_metrics(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MarketingDashboard::class)
            ->assertSee('Active Campaigns')
            ->assertSee('3')
            ->assertSee('1,520')
            ->assertSee('34.5');
    }

    public function test_displays_social_analytics(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MarketingDashboard::class)
            ->assertSee('Social Analytics')
            ->assertSee('twitter')
            ->assertSee('linkedin')
            ->assertSee('facebook');
    }

    public function test_displays_content_calendar(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MarketingDashboard::class)
            ->assertSee('Content Calendar')
            ->assertSee('Product Launch Tweet')
            ->assertSee('March Newsletter');
    }

    public function test_navigation_registered(): void
    {
        $this->assertEquals('Marketing', MarketingDashboard::getNavigationGroup());
        $this->assertEquals('heroicon-o-megaphone', MarketingDashboard::getNavigationIcon());
    }

    public function test_refresh_data_action(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(MarketingDashboard::class)
            ->call('refreshData')
            ->assertHasNoErrors();
    }
}
