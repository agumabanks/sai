<?php

namespace Tests\Feature;

use App\Filament\Pages\AlertConfig;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class AlertConfigTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub that returns realistic alert rule data for all API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getAlertRules(): array
            {
                return [
                    [
                        'id' => 1,
                        'name' => 'High CPU Alert',
                        'condition' => 'cpu_usage > threshold',
                        'threshold' => 90.0,
                        'severity' => 'critical',
                        'recipients' => ['admin@sanaa.co', 'ops@sanaa.co'],
                        'escalation_policy' => ['tiers' => [['channel' => 'email', 'delay_minutes' => 0], ['channel' => 'whatsapp', 'delay_minutes' => 15]]],
                        'quiet_hours' => ['start' => '22:00', 'end' => '06:00', 'timezone' => 'Africa/Nairobi'],
                        'enabled' => true,
                        'created_at' => '2026-03-14T10:00:00+00:00',
                        'updated_at' => '2026-03-14T10:00:00+00:00',
                    ],
                    [
                        'id' => 2,
                        'name' => 'Memory Warning',
                        'condition' => 'memory_usage > threshold',
                        'threshold' => 85.0,
                        'severity' => 'high',
                        'recipients' => ['admin@sanaa.co'],
                        'escalation_policy' => null,
                        'quiet_hours' => null,
                        'enabled' => true,
                        'created_at' => '2026-03-14T09:00:00+00:00',
                        'updated_at' => '2026-03-14T09:00:00+00:00',
                    ],
                    [
                        'id' => 3,
                        'name' => 'Disk Space Low',
                        'condition' => 'disk_usage > threshold',
                        'threshold' => 95.0,
                        'severity' => 'medium',
                        'recipients' => ['ops@sanaa.co'],
                        'escalation_policy' => null,
                        'quiet_hours' => null,
                        'enabled' => false,
                        'created_at' => '2026-03-14T08:00:00+00:00',
                        'updated_at' => '2026-03-14T08:00:00+00:00',
                    ],
                ];
            }

            public function createAlertRule(array $data): array
            {
                return [
                    'id' => 4,
                    'name' => $data['name'] ?? 'New Rule',
                    'condition' => $data['condition'] ?? '',
                    'threshold' => $data['threshold'] ?? 0,
                    'severity' => $data['severity'] ?? 'low',
                    'recipients' => $data['recipients'] ?? [],
                    'escalation_policy' => $data['escalation_policy'] ?? null,
                    'quiet_hours' => $data['quiet_hours'] ?? null,
                    'enabled' => $data['enabled'] ?? true,
                    'created_at' => '2026-03-14T12:00:00+00:00',
                    'updated_at' => '2026-03-14T12:00:00+00:00',
                ];
            }

            public function updateAlertRule(int $id, array $data): array
            {
                return array_merge([
                    'id' => $id,
                    'name' => 'Updated Rule',
                    'condition' => 'cpu_usage > threshold',
                    'threshold' => 90.0,
                    'severity' => 'critical',
                    'recipients' => ['admin@sanaa.co'],
                    'escalation_policy' => null,
                    'quiet_hours' => null,
                    'enabled' => true,
                    'created_at' => '2026-03-14T10:00:00+00:00',
                    'updated_at' => '2026-03-14T12:00:00+00:00',
                ], $data);
            }

            public function deleteAlertRule(int $id): array
            {
                return ['detail' => 'Alert rule deleted', 'id' => $id];
            }
        });
    }

    public function test_page_loads(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->assertSuccessful();
    }

    public function test_displays_alert_rules(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->assertSee('High CPU Alert')
            ->assertSee('Memory Warning')
            ->assertSee('Disk Space Low');
    }

    public function test_displays_severity_badges(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->assertSee('critical')
            ->assertSee('high')
            ->assertSee('medium');
    }

    public function test_displays_recipients(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->assertSee('admin@sanaa.co')
            ->assertSee('ops@sanaa.co');
    }

    public function test_create_rule_form_fields(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->call('showCreateForm')
            ->assertSet('showForm', true)
            ->assertSet('editingRuleId', null);
    }

    public function test_create_rule(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->call('showCreateForm')
            ->set('formName', 'New Alert Rule')
            ->set('formCondition', 'api_errors > threshold')
            ->set('formThreshold', '50')
            ->set('formSeverity', 'high')
            ->set('formRecipients', 'admin@sanaa.co, ops@sanaa.co')
            ->call('saveRule')
            ->assertHasNoErrors();
    }

    public function test_edit_rule(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->call('editRule', 1)
            ->assertSet('showForm', true)
            ->assertSet('editingRuleId', 1)
            ->assertSet('formName', 'High CPU Alert');
    }

    public function test_delete_rule(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->call('deleteRule', 1)
            ->assertHasNoErrors();
    }

    public function test_cancel_form(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->call('showCreateForm')
            ->assertSet('showForm', true)
            ->call('cancelForm')
            ->assertSet('showForm', false)
            ->assertSet('editingRuleId', null);
    }

    public function test_navigation_registered(): void
    {
        $this->assertEquals('System', AlertConfig::getNavigationGroup());
        $this->assertEquals('heroicon-o-bell-alert', AlertConfig::getNavigationIcon());
    }

    public function test_refresh_data(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->call('refreshData')
            ->assertHasNoErrors();
    }

    public function test_displays_enabled_status(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(AlertConfig::class)
            ->assertSee('Enabled')
            ->assertSee('Disabled');
    }
}
