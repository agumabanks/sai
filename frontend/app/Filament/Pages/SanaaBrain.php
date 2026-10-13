<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class SanaaBrain extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-cpu-chip';

    protected static ?string $navigationGroup = 'Intelligence';

    protected static ?int $navigationSort = 2;

    protected static string $view = 'filament.pages.sanaa-brain';

    protected static ?string $title = 'SanaaBrain';

    protected static ?string $navigationLabel = 'SanaaBrain';

    protected static ?string $slug = 'sanaa-brain';

    // ── Page state ────────────────────────────────────────────────────────

    /** Active section: add | search | briefing | all | session | smart | insights | learn | habits */
    public string $activeSection = 'all';

    /** Add memory form fields */
    public string $addContent = '';

    public string $addCategory = 'general';

    public string $addProject = '';

    public float $addConfidence = 1.0;

    /** Search */
    public string $searchQuery = '';

    public string $searchProject = '';

    public array $searchResults = [];

    /** Briefing */
    public string $briefingProject = '';

    public array $briefingData = [];

    /** All memories list */
    public string $filterProject = '';

    public string $filterCategory = '';

    public array $memoriesAll = [];

    public int $memoriesTotal = 0;

    /** Session save */
    public string $sessionContent = '';

    public string $sessionId = 'admin:sanaa-brain';

    public string $sessionProject = '';

    /** Smart Briefing (Phase 2) */
    public string $smartBriefingProject = '';

    public array $smartBriefingData = [];

    /** Auto-Learned Insights (Phase 2) */
    public array $insightsData = [];

    public string $insightsCategoryFilter = '';

    public string $insightsProjectFilter = '';

    /** Trigger Learn Now (Phase 2) */
    public array $learnNowResult = [];

    public bool $learnNowRunning = false;

    /** Habit Intelligence (Phase 2) */
    public array $habitsData = [];

    // ── Lifecycle ─────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadAllMemories();
    }

    // ── Section switching ─────────────────────────────────────────────────

    public function switchSection(string $section): void
    {
        $this->activeSection = $section;
    }

    // ── Add memory ────────────────────────────────────────────────────────

    public function submitAddMemory(): void
    {
        if (trim($this->addContent) === '') {
            Notification::make()->title('Content is required')->danger()->send();

            return;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->addMemory(
            content: trim($this->addContent),
            category: $this->addCategory ?: 'general',
            project: $this->addProject ?: null,
            metadata: [],
            confidence: (float) $this->addConfidence,
        );

        if (isset($result['id'])) {
            Notification::make()
                ->title('Memory saved (ID '.$result['id'].')')
                ->success()
                ->send();

            $this->addContent = '';
            $this->addProject = '';
            $this->addCategory = 'general';
            $this->addConfidence = 1.0;
            $this->loadAllMemories();
        } else {
            $err = $result['error'] ?? $result['detail'] ?? 'Unknown error';
            Notification::make()->title('Failed: '.$err)->danger()->send();
        }
    }

    // ── Search ────────────────────────────────────────────────────────────

    public function submitSearch(): void
    {
        if (trim($this->searchQuery) === '') {
            Notification::make()->title('Enter a search query')->warning()->send();

            return;
        }

        $engine = app(SanaaEngineService::class);
        $this->searchResults = $engine->searchMemory(
            query: trim($this->searchQuery),
            limit: 15,
            project: $this->searchProject ?: null,
        );
    }

    public function clearSearch(): void
    {
        $this->searchQuery = '';
        $this->searchProject = '';
        $this->searchResults = [];
    }

    // ── Briefing ──────────────────────────────────────────────────────────

    public function loadBriefing(): void
    {
        if (trim($this->briefingProject) === '') {
            Notification::make()->title('Enter a project name')->warning()->send();

            return;
        }

        $engine = app(SanaaEngineService::class);
        $this->briefingData = $engine->getMemoryBriefing(trim($this->briefingProject));
    }

    // ── All memories ──────────────────────────────────────────────────────

    public function loadAllMemories(): void
    {
        $engine = app(SanaaEngineService::class);
        $data = $engine->getAllMemories(
            project: $this->filterProject ?: null,
            category: $this->filterCategory ?: null,
            limit: 50,
        );

        $this->memoriesAll = $data['memories'] ?? [];
        $this->memoriesTotal = (int) ($data['total'] ?? 0);
    }

    public function updatedFilterProject(): void
    {
        $this->loadAllMemories();
    }

    public function updatedFilterCategory(): void
    {
        $this->loadAllMemories();
    }

    public function deleteMemory(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->deleteMemory($id);

        if (isset($result['deleted']) && $result['deleted']) {
            Notification::make()->title('Memory deleted')->success()->send();
            $this->loadAllMemories();
        } else {
            $err = $result['error'] ?? $result['detail'] ?? 'Could not delete';
            Notification::make()->title('Error: '.$err)->danger()->send();
        }
    }

    public function clearProject(): void
    {
        if (trim($this->filterProject) === '') {
            Notification::make()->title('Set a project filter first to clear')->warning()->send();

            return;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->clearProjectMemory(trim($this->filterProject));

        if (isset($result['deleted'])) {
            Notification::make()
                ->title('Cleared '.$result['deleted'].' memories for project "'.$this->filterProject.'"')
                ->success()
                ->send();
            $this->loadAllMemories();
        } else {
            $err = $result['error'] ?? $result['detail'] ?? 'Could not clear';
            Notification::make()->title('Error: '.$err)->danger()->send();
        }
    }

    // ── Session save ──────────────────────────────────────────────────────

    public function submitSaveSession(): void
    {
        if (trim($this->sessionContent) === '') {
            Notification::make()->title('Session content is required')->danger()->send();

            return;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->saveMemorySession(
            content: trim($this->sessionContent),
            sessionId: $this->sessionId ?: 'admin:sanaa-brain',
            project: $this->sessionProject ?: null,
        );

        if (isset($result['id'])) {
            Notification::make()
                ->title('Session saved (ID '.$result['id'].')')
                ->success()
                ->send();
            $this->sessionContent = '';
            $this->loadAllMemories();
        } else {
            $err = $result['error'] ?? $result['detail'] ?? 'Unknown error';
            Notification::make()->title('Failed: '.$err)->danger()->send();
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    public function getCategoryBadge(string $category): array
    {
        return match ($category) {
            'fact' => [
                'color' => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20',
                'label' => 'Fact',
            ],
            'procedure' => [
                'color' => 'text-[#bf5af2] bg-[#bf5af2]/10 border-[#bf5af2]/20',
                'label' => 'Procedure',
            ],
            'preference' => [
                'color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                'label' => 'Preference',
            ],
            'observation' => [
                'color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                'label' => 'Observation',
            ],
            'session_log' => [
                'color' => 'text-[#64d2ff] bg-[#64d2ff]/10 border-[#64d2ff]/20',
                'label' => 'Session',
            ],
            default => [
                'color' => 'text-white/40 bg-white/5 border-white/10',
                'label' => ucfirst($category),
            ],
        };
    }

    public function formatTimestamp(?string $ts): string
    {
        if (! $ts) {
            return '—';
        }
        try {
            return (new \DateTime($ts))->format('M j, Y g:ia');
        } catch (\Exception) {
            return $ts;
        }
    }

    public function truncate(string $text, int $len = 160): string
    {
        return mb_strlen($text) <= $len ? $text : mb_substr($text, 0, $len).'…';
    }

    // ── Phase 2: Smart Briefing ───────────────────────────────────────────

    public function loadSmartBriefing(): void
    {
        if (trim($this->smartBriefingProject) === '') {
            Notification::make()->title('Enter a project name')->warning()->send();

            return;
        }

        $engine = app(SanaaEngineService::class);
        $this->smartBriefingData = $engine->getSmartBriefing(trim($this->smartBriefingProject));
    }

    // ── Phase 2: Auto-Learned Insights ────────────────────────────────────

    public function loadInsights(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->insightsData = $engine->getBrainInsights(
            $this->insightsCategoryFilter,
            $this->insightsProjectFilter
        );
    }

    public function updatedInsightsCategoryFilter(): void
    {
        $this->loadInsights();
    }

    public function updatedInsightsProjectFilter(): void
    {
        $this->loadInsights();
    }

    public function getInsightsCategoryBadge(string $cat): array
    {
        return match ($cat) {
            'system_health' => ['color' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20', 'label' => 'Health'],
            'skill_intelligence' => ['color' => 'text-[#bf5af2] bg-[#bf5af2]/10 border-[#bf5af2]/20', 'label' => 'Skill'],
            'client_intelligence' => ['color' => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20', 'label' => 'Client'],
            'resource_usage' => ['color' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20', 'label' => 'Resource'],
            'work_pattern' => ['color' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20', 'label' => 'Work'],
            'recurring_issues' => ['color' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20', 'label' => 'Issue'],
            'habit_intelligence' => ['color' => 'text-[#64d2ff] bg-[#64d2ff]/10 border-[#64d2ff]/20', 'label' => 'Habit'],
            default => ['color' => 'text-white/40 bg-white/5 border-white/10', 'label' => ucfirst($cat)],
        };
    }

    // ── Phase 2: Trigger Learn Now ────────────────────────────────────────

    public function triggerLearnNow(): void
    {
        $this->learnNowRunning = true;
        $this->learnNowResult = [];

        $engine = app(SanaaEngineService::class);
        $result = $engine->triggerLearnNow();

        $this->learnNowRunning = false;

        if (isset($result['memories_created'])) {
            $this->learnNowResult = $result;
            Notification::make()
                ->title("{$result['memories_created']} new insights stored")
                ->success()
                ->send();
            $this->loadAllMemories();
            $this->loadInsights();
        } elseif (isset($result['error'])) {
            $this->learnNowResult = $result;
            Notification::make()->title('Error: '.$result['error'])->danger()->send();
        } else {
            $this->learnNowResult = $result;
            Notification::make()->title('Learning triggered — check results below')->info()->send();
        }
    }

    // ── Phase 2: Habit Intelligence ────────────────────────────────────────

    public function loadHabits(): void
    {
        $engine = app(SanaaEngineService::class);
        $data = $engine->getBrainHabits();
        $this->habitsData = $data['habits'] ?? [];
    }
}
