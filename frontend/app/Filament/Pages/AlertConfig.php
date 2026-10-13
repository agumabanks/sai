<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class AlertConfig extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-bell-alert';

    protected static ?string $navigationGroup = 'System';

    protected static ?int $navigationSort = 25;

    protected static string $view = 'filament.pages.alert-config';

    protected static ?string $title = 'Alert Configuration';

    protected static ?string $navigationLabel = 'Alert Config';

    protected static ?string $slug = 'alert-config';

    // ── Page state ────────────────────────────────────────────────────────

    /** All alert rules from backend */
    public array $rules = [];

    /** Whether the create/edit form is visible */
    public bool $showForm = false;

    /** ID of the rule being edited (null = creating new) */
    public ?int $editingRuleId = null;

    // ── Form fields ───────────────────────────────────────────────────────

    public string $formName = '';

    public string $formCondition = '';

    public string $formThreshold = '';

    public string $formSeverity = 'medium';

    public string $formRecipients = '';

    public string $formEscalationPolicy = '';

    public string $formQuietHoursStart = '';

    public string $formQuietHoursEnd = '';

    public string $formQuietHoursTimezone = 'Africa/Nairobi';

    public bool $formEnabled = true;

    // ── Lifecycle ─────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->loadData();
    }

    // ── Data loading ──────────────────────────────────────────────────────

    public function loadData(): void
    {
        $engine = app(SanaaEngineService::class);
        $this->rules = $engine->getAlertRules();

        // Ensure it's a list, not an error response
        if (! is_array($this->rules) || (isset($this->rules['error']))) {
            $this->rules = [];
        }
    }

    // ── Actions ───────────────────────────────────────────────────────────

    public function showCreateForm(): void
    {
        $this->resetForm();
        $this->showForm = true;
        $this->editingRuleId = null;
    }

    public function editRule(int $id): void
    {
        $rule = collect($this->rules)->firstWhere('id', $id);

        if (! $rule) {
            Notification::make()->title('Rule not found')->danger()->send();

            return;
        }

        $this->editingRuleId = $id;
        $this->formName = $rule['name'] ?? '';
        $this->formCondition = $rule['condition'] ?? '';
        $this->formThreshold = (string) ($rule['threshold'] ?? '');
        $this->formSeverity = $rule['severity'] ?? 'medium';
        $this->formRecipients = is_array($rule['recipients'] ?? null)
            ? implode(', ', $rule['recipients'])
            : '';
        $this->formEnabled = $rule['enabled'] ?? true;

        // Escalation policy (JSON)
        $this->formEscalationPolicy = ! empty($rule['escalation_policy'])
            ? json_encode($rule['escalation_policy'], JSON_PRETTY_PRINT)
            : '';

        // Quiet hours
        $quietHours = $rule['quiet_hours'] ?? null;
        if (is_array($quietHours)) {
            $this->formQuietHoursStart = $quietHours['start'] ?? '';
            $this->formQuietHoursEnd = $quietHours['end'] ?? '';
            $this->formQuietHoursTimezone = $quietHours['timezone'] ?? 'Africa/Nairobi';
        } else {
            $this->formQuietHoursStart = '';
            $this->formQuietHoursEnd = '';
            $this->formQuietHoursTimezone = 'Africa/Nairobi';
        }

        $this->showForm = true;
    }

    public function saveRule(): void
    {
        $engine = app(SanaaEngineService::class);

        // Parse recipients from comma-separated string
        $recipients = array_values(array_filter(
            array_map('trim', explode(',', $this->formRecipients)),
            fn (string $r): bool => $r !== ''
        ));

        // Build quiet hours if provided
        $quietHours = null;
        if ($this->formQuietHoursStart && $this->formQuietHoursEnd) {
            $quietHours = [
                'start' => $this->formQuietHoursStart,
                'end' => $this->formQuietHoursEnd,
                'timezone' => $this->formQuietHoursTimezone,
            ];
        }

        // Build escalation policy if provided
        $escalationPolicy = null;
        if ($this->formEscalationPolicy) {
            $decoded = json_decode($this->formEscalationPolicy, true);
            if (is_array($decoded)) {
                $escalationPolicy = $decoded;
            }
        }

        $data = [
            'name' => $this->formName,
            'condition' => $this->formCondition,
            'threshold' => (float) $this->formThreshold,
            'severity' => $this->formSeverity,
            'recipients' => $recipients,
            'escalation_policy' => $escalationPolicy,
            'quiet_hours' => $quietHours,
            'enabled' => $this->formEnabled,
        ];

        if ($this->editingRuleId) {
            $result = $engine->updateAlertRule($this->editingRuleId, $data);
            $action = 'updated';
        } else {
            $result = $engine->createAlertRule($data);
            $action = 'created';
        }

        if (isset($result['error'])) {
            Notification::make()
                ->title("Failed to {$action} rule")
                ->body($result['error'])
                ->danger()
                ->send();

            return;
        }

        Notification::make()
            ->title("Alert rule {$action}")
            ->success()
            ->send();

        $this->cancelForm();
        $this->loadData();
    }

    public function deleteRule(int $id): void
    {
        $engine = app(SanaaEngineService::class);
        $result = $engine->deleteAlertRule($id);

        if (isset($result['error'])) {
            Notification::make()
                ->title('Failed to delete rule')
                ->body($result['error'])
                ->danger()
                ->send();

            return;
        }

        Notification::make()
            ->title('Alert rule deleted')
            ->success()
            ->send();

        $this->loadData();
    }

    public function cancelForm(): void
    {
        $this->showForm = false;
        $this->editingRuleId = null;
        $this->resetForm();
    }

    public function refreshData(): void
    {
        $this->loadData();
        Notification::make()->title('Alert rules refreshed')->success()->send();
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    protected function resetForm(): void
    {
        $this->formName = '';
        $this->formCondition = '';
        $this->formThreshold = '';
        $this->formSeverity = 'medium';
        $this->formRecipients = '';
        $this->formEscalationPolicy = '';
        $this->formQuietHoursStart = '';
        $this->formQuietHoursEnd = '';
        $this->formQuietHoursTimezone = 'Africa/Nairobi';
        $this->formEnabled = true;
    }

    /**
     * Get CSS classes for a severity badge.
     */
    public function getSeverityBadge(string $severity): string
    {
        return match (strtolower($severity)) {
            'critical' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
            'high' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
            'medium' => 'text-[#ffd60a] bg-[#ffd60a]/10 border-[#ffd60a]/20',
            'low' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
            default => 'text-white/40 bg-white/5 border-white/10',
        };
    }

    /**
     * Format a timestamp for display.
     */
    public function formatTimestamp(?string $timestamp): string
    {
        if (! $timestamp) {
            return '—';
        }
        try {
            $dt = new \DateTime($timestamp);

            return $dt->format('M j, Y H:i');
        } catch (\Exception $e) {
            return $timestamp;
        }
    }

    /**
     * Get rule count.
     */
    public function getRuleCount(): int
    {
        return count($this->rules);
    }

    /**
     * Get enabled rules count.
     */
    public function getEnabledCount(): int
    {
        return count(array_filter($this->rules, fn (array $r): bool => ($r['enabled'] ?? false)));
    }
}
