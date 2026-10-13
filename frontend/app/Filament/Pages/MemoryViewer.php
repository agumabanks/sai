<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class MemoryViewer extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-light-bulb';

    protected static ?string $navigationGroup = 'Intelligence';

    protected static ?int $navigationSort = 3;

    protected static string $view = 'filament.pages.memory-viewer';

    protected static ?string $title = 'Memory Viewer';

    protected static ?string $navigationLabel = 'Memory Viewer';

    // ── Page state ────────────────────────────────────────────────────────

    /** Current active tab: memories | learning-logs | promoted */
    public string $activeTab = 'memories';

    /** Memories data from API */
    public array $memoriesData = [];

    /** Learning logs data from API */
    public array $learningLogsData = [];

    /** Search query for memories */
    public string $searchQuery = '';

    /** Category filter for memories */
    public string $categoryFilter = '';

    /** Log type filter for learning logs */
    public string $logTypeFilter = '';

    // ── Lifecycle ─────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadData();
    }

    // ── Data loading ──────────────────────────────────────────────────────

    public function loadData(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->memoriesData = $engine->getMemories(
            $this->searchQuery ?: null,
            $this->categoryFilter ?: null
        );
        $this->learningLogsData = $engine->getLearningLogs(
            $this->logTypeFilter ?: null
        );
    }

    public function refreshData(): void
    {
        $this->loadData();
        Notification::make()->title('Memory data refreshed')->success()->send();
    }

    // ── Tab switching ─────────────────────────────────────────────────────

    public function switchTab(string $tab): void
    {
        $this->activeTab = $tab;
    }

    // ── Filters ───────────────────────────────────────────────────────────

    public function updatedSearchQuery(): void
    {
        $this->loadData();
    }

    public function updatedCategoryFilter(): void
    {
        $this->loadData();
    }

    public function updatedLogTypeFilter(): void
    {
        $this->loadData();
    }

    public function clearFilters(): void
    {
        $this->searchQuery = '';
        $this->categoryFilter = '';
        $this->logTypeFilter = '';
        $this->loadData();
    }

    // ── Helpers: Memories ─────────────────────────────────────────────────

    /**
     * Get the list of memories from API response.
     */
    public function getMemories(): array
    {
        return $this->memoriesData['memories'] ?? [];
    }

    /**
     * Get total memory count.
     */
    public function getMemoryCount(): int
    {
        return (int) ($this->memoriesData['total'] ?? 0);
    }

    /**
     * Get the confidence badge styling.
     */
    public function getConfidenceBadge(float $confidence): array
    {
        if ($confidence >= 0.8) {
            return [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'label' => 'High',
            ];
        }
        if ($confidence >= 0.5) {
            return [
                'color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                'label' => 'Medium',
            ];
        }

        return [
            'color' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
            'label' => 'Low',
        ];
    }

    /**
     * Get the category badge styling.
     */
    public function getCategoryBadge(string $category): array
    {
        return match ($category) {
            'fact' => [
                'color' => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20',
                'icon' => 'heroicon-o-check-badge',
            ],
            'procedure' => [
                'color' => 'text-[#bf5af2] bg-[#bf5af2]/10 border-[#bf5af2]/20',
                'icon' => 'heroicon-o-cog-6-tooth',
            ],
            'preference' => [
                'color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                'icon' => 'heroicon-o-heart',
            ],
            'observation' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'icon' => 'heroicon-o-eye',
            ],
            default => [
                'color' => 'text-white/40 bg-white/5 border-white/10',
                'icon' => 'heroicon-o-tag',
            ],
        };
    }

    // ── Helpers: Learning Logs ─────────────────────────────────────────────

    /**
     * Get all learning log entries.
     */
    public function getLearningEntries(): array
    {
        return $this->learningLogsData['entries'] ?? [];
    }

    /**
     * Get promoted learning entries.
     */
    public function getPromotedEntries(): array
    {
        return $this->learningLogsData['promoted'] ?? [];
    }

    /**
     * Get promoted count.
     */
    public function getPromotedCount(): int
    {
        return (int) ($this->learningLogsData['promoted_count'] ?? 0);
    }

    /**
     * Get learning log type badge styling.
     */
    public function getLogTypeBadge(string $logType): array
    {
        return match ($logType) {
            'LEARNINGS' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'icon' => 'heroicon-o-academic-cap',
                'label' => 'Learning',
            ],
            'ERRORS' => [
                'color' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                'icon' => 'heroicon-o-exclamation-triangle',
                'label' => 'Error',
            ],
            'FEATURE_REQUESTS' => [
                'color' => 'text-[#bf5af2] bg-[#bf5af2]/10 border-[#bf5af2]/20',
                'icon' => 'heroicon-o-sparkles',
                'label' => 'Feature Request',
            ],
            default => [
                'color' => 'text-white/40 bg-white/5 border-white/10',
                'icon' => 'heroicon-o-document-text',
                'label' => ucfirst(strtolower($logType)),
            ],
        };
    }

    /**
     * Format a timestamp for display.
     */
    public function formatTimestamp(?string $timestamp): string
    {
        if (! $timestamp) {
            return 'Unknown';
        }

        try {
            $dt = new \DateTime($timestamp);

            return $dt->format('M j, Y g:ia');
        } catch (\Exception $e) {
            return $timestamp;
        }
    }

    /**
     * Truncate text to a given length.
     */
    public function truncateText(string $text, int $length = 200): string
    {
        if (mb_strlen($text) <= $length) {
            return $text;
        }

        return mb_substr($text, 0, $length).'…';
    }
}
