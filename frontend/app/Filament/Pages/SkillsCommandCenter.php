<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class SkillsCommandCenter extends Page
{
    private const QUICK_ACTIONS = [
        'healthcheck_all' => [
            'label' => 'Healthcheck All',
            'icon' => '📡',
            'description' => 'Run platform endpoint and service checks across the estate.',
            'skill' => 'healthcheck',
            'args' => ['action' => 'check_all'],
        ],
        'llm_cost_summary' => [
            'label' => 'LLM Cost Summary',
            'icon' => '💰',
            'description' => 'Review AI spend, usage drift, and cost-heavy sessions.',
            'skill' => 'session_logs',
            'args' => ['action' => 'cost_summary'],
        ],
        'error_analysis' => [
            'label' => 'Error Analysis',
            'icon' => '🔬',
            'description' => 'Pull the latest backend errors and cluster likely failure patterns.',
            'skill' => 'session_logs',
            'args' => ['action' => 'error_analysis', 'limit' => 10],
        ],
        'project_tasks' => [
            'label' => 'Task List',
            'icon' => '📋',
            'description' => 'Inspect the current tracked work and pending execution tasks.',
            'skill' => 'project_manager',
            'args' => ['action' => 'list'],
        ],
        'watched_sites' => [
            'label' => 'Check Watched Sites',
            'icon' => '👁',
            'description' => 'Ping the monitored Sanaa properties and report visible downtime.',
            'skill' => 'site_watcher',
            'args' => ['action' => 'check_now'],
        ],
        'tmux_sessions' => [
            'label' => 'Tmux Sessions',
            'icon' => '🖥',
            'description' => 'List the current long-running sessions and worker consoles.',
            'skill' => 'tmux_runner',
            'args' => ['action' => 'list'],
        ],
        'skills_directory' => [
            'label' => 'List Skills Dir',
            'icon' => '🗂',
            'description' => 'Inspect the backend skills directory and current generated skills.',
            'skill' => 'coding_agent',
            'args' => ['action' => 'list', 'directory' => '/var/www/ai.sanaa.co/backend/skills'],
        ],
        'endpoint_registry' => [
            'label' => 'Endpoint Registry',
            'icon' => '🗃',
            'description' => 'Review the endpoint inventory the healthcheck system is tracking.',
            'skill' => 'healthcheck',
            'args' => ['action' => 'list_endpoints'],
        ],
        'tenant_sync_status' => [
            'label' => 'Tenant Sync Status',
            'icon' => '🔄',
            'description' => 'Compare tenant drift before you pull, sync, or propagate a tested fix.',
            'skill' => 'sanaa_tenant_sync',
            'args' => ['action' => 'status', 'source_tenant' => 'kasawo', 'targets' => 'all'],
        ],
        'sanaa_doctor' => [
            'label' => 'Doctor Briefing',
            'icon' => '🩺',
            'description' => 'Generate the ecosystem readiness briefing with risk predictions and next actions.',
            'skill' => 'sanaa_doctor',
            'args' => [
                'action' => 'ecosystem_report',
                'tenant' => 'all',
                'lint_scope' => 'last_commit',
                'report_channel' => 'none',
                'include_ml' => true,
                'detail_level' => 'full',
            ],
        ],
    ];

    protected static ?string $navigationIcon = 'heroicon-o-bolt';

    protected static ?string $navigationGroup = 'Skills Lab';

    protected static ?int $navigationSort = 1;

    protected static string $view = 'filament.pages.skills-command-center';

    protected static ?string $title = 'Skills Command Center';

    protected static ?string $navigationLabel = 'Skills';

    // ── Page state ────────────────────────────────────────────────────────────

    /** All registered skills returned from the API */
    public array $skills = [];

    /** Recent skill runs text output */
    public string $runsOutput = '';

    /** The skill currently selected for execution */
    public ?array $selectedSkill = null;

    /** JSON string of args for the selected skill */
    public string $skillArgs = '{}';

    /** Output from the last skill execution */
    public string $skillOutput = '';

    /** Whether the fullscreen workspace modal is open */
    public bool $showWorkspace = false;

    /** Whether we're waiting on a skill to execute */
    public bool $isRunning = false;

    /** Whether the create-skill panel is open */
    public bool $showCreatePanel = false;

    /** New skill name input */
    public string $newSkillName = '';

    /** New skill description input */
    public string $newSkillDescription = '';

    /** Category filter: '' = all */
    public string $categoryFilter = '';

    /** Search filter */
    public string $searchFilter = '';

    /** Catalog loading error */
    public string $loadError = '';

    /** Where the current workspace was opened from */
    public string $workspaceSource = 'page';

    /** ML scores keyed by skill name */
    public array $mlScores = [];

    /** Global learning log entries */
    public array $learningLog = [];

    /** Current skill's detailed ML data */
    public array $skillMLData = [];

    /** Active tab: 'catalog' or 'intelligence' */
    public string $activeTab = 'catalog';

    /** Feedback rating for current skill (-1, 0, 1 for thumbs) */
    public int $feedbackRating = 0;

    /** Feedback comment */
    public string $feedbackComment = '';

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadSkills();

        try {
            $this->loadMLScores();
        } catch (\Throwable $e) {
            // ML scores are optional; don't block page load
        }

        $skillName = trim((string) request()->query('skill', ''));
        $argsJson = request()->query('args');
        $source = trim((string) request()->query('source', ''));

        if ($skillName !== '') {
            $this->workspaceSource = $source !== '' ? $source : 'page';
            $this->selectSkill($skillName, is_string($argsJson) ? $argsJson : null);
        }
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    public function loadSkills(): void
    {
        $engine = app(SanaaEngineService::class);
        $data = $engine->getSkillCatalog();
        $this->skills = $data['skills'] ?? [];
        $this->loadError = (string) ($data['error'] ?? '');

        if ($this->selectedSkill) {
            $this->selectedSkill = $engine->getSkillDefinition((string) ($this->selectedSkill['name'] ?? ''))
                ?? $this->findSkill((string) ($this->selectedSkill['name'] ?? ''));
        }
    }

    public function refreshData(): void
    {
        $this->loadSkills();
        $this->runsOutput = '';
        Notification::make()->title('Skills refreshed')->success()->send();
    }

    public function loadRecentRuns(): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->getSkillRuns(25);
        $this->runsOutput = (string) ($result['output'] ?? ($result['error'] ?? 'No data'));
    }

    // ── Skill selection ───────────────────────────────────────────────────────

    public function selectSkill(string $skillName, ?string $argsJson = null): void
    {
        $summary = $this->findSkill($skillName);
        $skill = app(SanaaEngineService::class)->getSkillDefinition($skillName) ?? $summary;

        if ($skill) {
            $this->selectedSkill = $skill;
            $this->skillOutput = '';
            $this->skillArgs = $this->normalizeArgsJson(
                $argsJson,
                $this->formatSkillArgs($skill['parameters'] ?? []),
            );
            $this->showWorkspace = true;

            try {
                $this->loadSkillML($skillName);
            } catch (\Throwable $e) {
                // ML data is optional
            }
        }
    }

    public function clearSelection(): void
    {
        $this->selectedSkill = null;
        $this->skillArgs = '{}';
        $this->skillOutput = '';
        $this->showWorkspace = false;
        $this->workspaceSource = 'page';
    }

    public function closeWorkspace(): void
    {
        $this->showWorkspace = false;
    }

    // ── Skill execution ───────────────────────────────────────────────────────

    public function runSelectedSkill(): void
    {
        if (! $this->selectedSkill) {
            Notification::make()->title('No skill selected')->warning()->send();

            return;
        }

        $this->isRunning = true;
        $skillName = (string) ($this->selectedSkill['name'] ?? '');

        // Parse args
        $args = [];
        $decoded = json_decode($this->skillArgs, true);
        if (json_last_error() === JSON_ERROR_NONE && is_array($decoded)) {
            $args = $decoded;
        } else {
            $this->isRunning = false;
            Notification::make()
                ->title('Invalid JSON args')
                ->body('Please fix the JSON in the args field.')
                ->danger()
                ->send();

            return;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->runSkill($skillName, $args);

        $success = (bool) ($result['success'] ?? false);
        $output = (string) ($result['output'] ?? '');
        $error = (string) ($result['error'] ?? '');

        if ($success) {
            $this->skillOutput = $output ?: '(no output)';
            Notification::make()
                ->title("Skill '{$skillName}' executed")
                ->success()
                ->send();
        } else {
            $needsApproval = (bool) ($result['data']['policy_denied'] ?? false)
                || (bool) ($result['needs_approval'] ?? false);

            if ($needsApproval) {
                $this->skillOutput = "⚠ APPROVAL REQUIRED\n\n".
                    ($result['approval_prompt'] ?? $error);
                Notification::make()
                    ->title("Skill '{$skillName}' needs approval")
                    ->body('This skill requires manual approval before execution.')
                    ->warning()
                    ->send();
            } else {
                $this->skillOutput = "ERROR: {$error}";
                Notification::make()
                    ->title("Skill '{$skillName}' failed")
                    ->body($error)
                    ->danger()
                    ->send();
            }
        }

        $this->isRunning = false;
    }

    // ── Quick-run actions (pre-filled helpers) ────────────────────────────────

    public function runQuickAction(string $actionKey): void
    {
        $action = self::QUICK_ACTIONS[$actionKey] ?? null;

        if (! $action) {
            Notification::make()->title('Unknown quick action')->danger()->send();

            return;
        }

        $this->selectSkill($action['skill']);
        $this->skillArgs = json_encode((object) $action['args'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
        $this->runSelectedSkill();
    }

    // ── Toggle skill enabled/disabled ─────────────────────────────────────────

    public function toggleSkill(string $skillName, bool $enabled): void
    {
        $engine = app(SanaaEngineService::class);
        $res = $engine->setSkillEnabled($skillName, $enabled);

        if (! empty($res['error'])) {
            Notification::make()->title('Toggle failed')->body((string) $res['error'])->danger()->send();

            return;
        }

        Notification::make()
            ->title("Skill '{$skillName}' ".($enabled ? 'enabled' : 'disabled'))
            ->success()
            ->send();

        $this->loadSkills();
    }

    // ── Hot-reload ────────────────────────────────────────────────────────────

    public function hotReload(string $skillName): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->hotReloadSkill($skillName);

        if ($result['success'] ?? false) {
            Notification::make()
                ->title("Hot-reloaded: {$skillName}")
                ->body((string) ($result['output'] ?? ''))
                ->success()
                ->send();
            $this->loadSkills();
        } else {
            Notification::make()
                ->title("Hot-reload failed: {$skillName}")
                ->body((string) ($result['error'] ?? 'Unknown error'))
                ->danger()
                ->send();
        }
    }

    // ── Create new skill ──────────────────────────────────────────────────────

    public function createSkill(): void
    {
        $name = trim($this->newSkillName);
        $desc = trim($this->newSkillDescription);

        if (! $name || ! $desc) {
            Notification::make()
                ->title('Skill name and description are required')
                ->warning()
                ->send();

            return;
        }

        // Normalise: snake_case
        $name = strtolower(preg_replace('/[\s\-]+/', '_', $name));

        $this->isRunning = true;
        $engine = app(SanaaEngineService::class);
        $result = $engine->createSkill($name, $desc);
        $this->isRunning = false;

        if ($result['success'] ?? false) {
            Notification::make()
                ->title("Skill '{$name}' created!")
                ->body((string) ($result['output'] ?? 'See skills list.'))
                ->success()
                ->send();
            $this->newSkillName = '';
            $this->newSkillDescription = '';
            $this->showCreatePanel = false;
            $this->loadSkills();
        } else {
            Notification::make()
                ->title('Skill creation failed')
                ->body((string) ($result['error'] ?? 'Unknown error'))
                ->danger()
                ->send();
        }
    }

    // ── ML Self-Learning ──────────────────────────────────────────────────────

    public function loadMLScores(): void
    {
        $engine = app(SanaaEngineService::class);
        $data = $engine->getMLScores();
        $scores = $data['scores'] ?? [];

        $this->mlScores = [];
        foreach ($scores as $s) {
            $name = $s['skill_name'] ?? '';
            if ($name !== '') {
                $this->mlScores[$name] = $s;
            }
        }
    }

    public function loadLearningLog(): void
    {
        $engine = app(SanaaEngineService::class);
        $data = $engine->getGlobalLearningLog(30);
        $this->learningLog = $data['events'] ?? [];
    }

    public function loadSkillML(string $skillName): void
    {
        $engine = app(SanaaEngineService::class);
        $this->skillMLData = $engine->getSkillMLScore($skillName);
    }

    public function triggerMLAnalysis(): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->triggerMLAnalysis();

        if (! empty($result['error'])) {
            Notification::make()->title('ML Analysis failed')->body((string) $result['error'])->danger()->send();

            return;
        }

        $analyzed = $result['skills_analyzed'] ?? 0;
        Notification::make()
            ->title("ML Analysis complete: {$analyzed} skills analyzed")
            ->success()
            ->send();

        $this->loadMLScores();
        $this->loadLearningLog();
    }

    public function submitFeedback(string $skillName, int $rating): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->submitSkillFeedback(
            $skillName,
            $rating,
            'thumbs',
            $this->feedbackComment ?: null,
        );

        if (! empty($result['error'])) {
            Notification::make()->title('Feedback failed')->body((string) $result['error'])->danger()->send();

            return;
        }

        $label = $rating > 0 ? 'positive' : ($rating < 0 ? 'negative' : 'neutral');
        Notification::make()
            ->title("Feedback recorded: {$label}")
            ->success()
            ->send();

        $this->feedbackComment = '';
        $this->feedbackRating = 0;
    }

    public function switchTab(string $tab): void
    {
        $this->activeTab = $tab;

        if ($tab === 'intelligence') {
            $this->loadMLScores();
            $this->loadLearningLog();
        }
    }

    public function getScoreColor(float $score): string
    {
        if ($score >= 0.8) {
            return 'emerald';
        }
        if ($score >= 0.6) {
            return 'sky';
        }
        if ($score >= 0.4) {
            return 'amber';
        }

        return 'rose';
    }

    public function getTrendIcon(string $trend): string
    {
        return match ($trend) {
            'improving' => '↗',
            'degrading' => '↘',
            default => '→',
        };
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    public function getFilteredSkills(): array
    {
        $skills = $this->skills;

        if ($this->categoryFilter !== '') {
            $skills = array_filter($skills, fn ($s) => ($s['category'] ?? '') === $this->categoryFilter
            );
        }

        if ($this->searchFilter !== '') {
            $q = strtolower($this->searchFilter);
            $skills = array_filter($skills, function ($s) use ($q) {
                $haystack = strtolower(
                    ($s['name'] ?? '').' '.
                    ($s['description'] ?? '').' '.
                    implode(' ', $s['tags'] ?? [])
                );

                return str_contains($haystack, $q);
            });
        }

        return array_values($skills);
    }

    public function getCategories(): array
    {
        $cats = array_unique(array_column($this->skills, 'category'));
        sort($cats);

        return array_values(array_filter($cats));
    }

    /** Category → Heroicon mapping */
    public function categoryIcon(string $category): string
    {
        return match ($category) {
            'development' => 'heroicon-o-code-bracket',
            'monitoring' => 'heroicon-o-signal',
            'communication' => 'heroicon-o-chat-bubble-left-right',
            'productivity' => 'heroicon-o-clipboard-document-list',
            'research' => 'heroicon-o-magnifying-glass',
            'meta' => 'heroicon-o-cpu-chip',
            'system' => 'heroicon-o-server',
            default => 'heroicon-o-bolt',
        };
    }

    public function getQuickActions(): array
    {
        return self::QUICK_ACTIONS;
    }

    public function getCatalogSnapshot(): array
    {
        $total = count($this->skills);
        $enabled = count(array_filter($this->skills, fn (array $skill) => ($skill['enabled'] ?? true) !== false));
        $ops = count(array_filter($this->skills, fn (array $skill) => in_array(($skill['category'] ?? ''), ['monitoring', 'system'], true)));
        $mlTracked = count($this->mlScores);

        return [
            ['label' => 'Registered Skills', 'value' => $total, 'tone' => 'sky'],
            ['label' => 'Enabled Live', 'value' => $enabled, 'tone' => 'emerald'],
            ['label' => 'Ops Ready', 'value' => $ops, 'tone' => 'amber'],
            ['label' => 'ML Tracked', 'value' => $mlTracked, 'tone' => 'slate'],
        ];
    }

    public function getFeaturedSkills(): array
    {
        $featured = [
            'sanaa_doctor',
            'sanaa_tenant_sync',
            'healthcheck',
            'team_broadcast',
        ];

        $cards = [];
        foreach ($featured as $skillName) {
            $skill = $this->findSkill($skillName);
            if ($skill) {
                $cards[] = $skill;
            }
        }

        return $cards;
    }

    protected function findSkill(string $skillName): ?array
    {
        foreach ($this->skills as $skill) {
            if (($skill['name'] ?? '') === $skillName) {
                return $skill;
            }
        }

        return null;
    }

    protected function formatSkillArgs(array $parameters): string
    {
        $template = [];

        foreach ($parameters as $name => $schema) {
            if (($schema['required'] ?? false) || array_key_exists('default', $schema)) {
                $template[$name] = $schema['default'] ?? '';
            }
        }

        if ($template === []) {
            return '{}';
        }

        return json_encode((object) $template, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    }

    protected function normalizeArgsJson(?string $argsJson, string $fallback): string
    {
        if (! is_string($argsJson) || trim($argsJson) === '') {
            return $fallback;
        }

        $decoded = json_decode($argsJson, true);

        if (json_last_error() !== JSON_ERROR_NONE || ! is_array($decoded)) {
            return $fallback;
        }

        return json_encode((object) $decoded, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    }
}
