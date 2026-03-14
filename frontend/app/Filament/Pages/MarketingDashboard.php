<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class MarketingDashboard extends Page
{
    protected static ?string $navigationIcon    = 'heroicon-o-megaphone';
    protected static ?string $navigationGroup   = 'Marketing';
    protected static ?int    $navigationSort    = 1;
    protected static string  $view              = 'filament.pages.marketing-dashboard';
    protected static ?string $title             = 'Marketing Dashboard';
    protected static ?string $navigationLabel   = 'Marketing Dashboard';

    // ── Page state ────────────────────────────────────────────────────────

    /** Campaign and email marketing metrics */
    public array $metrics = [];

    /** Social media analytics */
    public array $socialAnalytics = [];

    /** Scheduled content calendar */
    public array $scheduledContent = [];

    // ── Lifecycle ─────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadData();
    }

    // ── Data loading ──────────────────────────────────────────────────────

    public function loadData(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->metrics = $engine->getMarketingMetrics();
        $this->socialAnalytics = $engine->getSocialAnalytics();
        $this->scheduledContent = $engine->getScheduledContent();
    }

    public function refreshData(): void
    {
        $this->loadData();
        Notification::make()->title('Marketing data refreshed')->success()->send();
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    /**
     * Get the active campaigns count.
     */
    public function getActiveCampaigns(): int
    {
        return (int) ($this->metrics['campaigns']['active'] ?? 0);
    }

    /**
     * Get total campaigns count.
     */
    public function getTotalCampaigns(): int
    {
        return (int) ($this->metrics['campaigns']['total'] ?? 0);
    }

    /**
     * Get draft campaigns count.
     */
    public function getDraftCampaigns(): int
    {
        return (int) ($this->metrics['campaigns']['draft'] ?? 0);
    }

    /**
     * Get sent campaigns count.
     */
    public function getSentCampaigns(): int
    {
        return (int) ($this->metrics['campaigns']['sent'] ?? 0);
    }

    /**
     * Get total emails sent.
     */
    public function getTotalSent(): int
    {
        return (int) ($this->metrics['email']['total_sent'] ?? 0);
    }

    /**
     * Get email open rate.
     */
    public function getOpenRate(): float
    {
        return (float) ($this->metrics['email']['open_rate'] ?? 0);
    }

    /**
     * Get email click rate.
     */
    public function getClickRate(): float
    {
        return (float) ($this->metrics['email']['click_rate'] ?? 0);
    }

    /**
     * Get email bounce rate.
     */
    public function getBounceRate(): float
    {
        return (float) ($this->metrics['email']['bounce_rate'] ?? 0);
    }

    /**
     * Get total social posts.
     */
    public function getTotalPosts(): int
    {
        return (int) ($this->socialAnalytics['total_posts'] ?? 0);
    }

    /**
     * Get platform breakdown data.
     */
    public function getPlatforms(): array
    {
        return $this->socialAnalytics['platforms'] ?? [];
    }

    /**
     * Get recent social posts.
     */
    public function getRecentPosts(): array
    {
        return $this->socialAnalytics['recent_posts'] ?? [];
    }

    /**
     * Get upcoming scheduled items.
     */
    public function getUpcomingItems(): array
    {
        return $this->scheduledContent['upcoming'] ?? [];
    }

    /**
     * Get the icon for a platform.
     */
    public function getPlatformIcon(string $platform): string
    {
        return match (strtolower($platform)) {
            'twitter' => 'heroicon-o-chat-bubble-left-right',
            'linkedin' => 'heroicon-o-briefcase',
            'facebook' => 'heroicon-o-user-group',
            'email' => 'heroicon-o-envelope',
            default => 'heroicon-o-globe-alt',
        };
    }

    /**
     * Get the gradient CSS for a platform.
     */
    public function getPlatformGradient(string $platform): string
    {
        return match (strtolower($platform)) {
            'twitter' => 'from-[#1DA1F2] to-[#0a84ff]',
            'linkedin' => 'from-[#0077b5] to-[#00a0dc]',
            'facebook' => 'from-[#1877F2] to-[#4267B2]',
            'email' => 'from-[#6366f1] to-[#a855f7]',
            default => 'from-[#6b7280] to-[#9ca3af]',
        };
    }

    /**
     * Get the CSS classes for a content status badge.
     */
    public function getStatusBadge(string $status): array
    {
        return match ($status) {
            'scheduled' => [
                'color' => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20',
                'dot' => 'bg-[#0a84ff]',
                'label' => 'Scheduled',
            ],
            'published' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'dot' => 'bg-[#30d158]',
                'label' => 'Published',
            ],
            'draft' => [
                'color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                'dot' => 'bg-[#ff9f0a]',
                'label' => 'Draft',
            ],
            'sent' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'dot' => 'bg-[#30d158]',
                'label' => 'Sent',
            ],
            'sending' => [
                'color' => 'text-[#bf5af2] bg-[#bf5af2]/10 border-[#bf5af2]/20',
                'dot' => 'bg-[#bf5af2]',
                'label' => 'Sending',
            ],
            default => [
                'color' => 'text-white/40 bg-white/5 border-white/10',
                'dot' => 'bg-white/40',
                'label' => ucfirst($status),
            ],
        };
    }

    /**
     * Format a scheduled time for display.
     */
    public function formatScheduledTime(?string $timestamp): string
    {
        if (!$timestamp) {
            return 'Not set';
        }

        try {
            $dt = new \DateTime($timestamp);
            return $dt->format('M j, Y g:ia');
        } catch (\Exception $e) {
            return $timestamp;
        }
    }
}
