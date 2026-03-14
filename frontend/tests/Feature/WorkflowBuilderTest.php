<?php

namespace Tests\Feature;

use App\Filament\Pages\WorkflowBuilder;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class WorkflowBuilderTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Stub the SanaaEngineService to avoid real API calls.
     */
    private function stubEngine(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getWorkflows(): array
            {
                return [
                    'count' => 2,
                    'workflows' => [
                        [
                            'name' => 'daily_triage',
                            'description' => 'Daily system health triage',
                            'version' => '1.0.0',
                            'step_count' => 5,
                            'steps' => [
                                ['id' => 'health_check', 'action' => 'skill', 'description' => 'Run health check', 'approval' => false, 'on_failure' => 'abort'],
                                ['id' => 'notify', 'action' => 'notify', 'description' => 'Send notification', 'approval' => false, 'on_failure' => 'abort'],
                            ],
                        ],
                        [
                            'name' => 'incident_response',
                            'description' => 'Automated incident response',
                            'version' => '1.0.0',
                            'step_count' => 6,
                            'steps' => [],
                        ],
                    ],
                ];
            }

            public function getSkills(): array
            {
                return [
                    'skills' => [
                        ['name' => 'server_health', 'description' => 'Server health check', 'enabled' => true],
                        ['name' => 'app_monitor', 'description' => 'Application monitor', 'enabled' => true],
                        ['name' => 'web_test', 'description' => 'Web endpoint test', 'enabled' => true],
                    ],
                    'tools' => [],
                    'tool_policy' => [],
                ];
            }

            public function saveWorkflow(string $yaml): array
            {
                if (empty(trim($yaml))) {
                    return ['error' => 'Empty YAML'];
                }
                // Check for basic workflow structure
                if (!str_contains($yaml, 'name:') || !str_contains($yaml, 'steps:')) {
                    return ['error' => 'Invalid workflow YAML'];
                }
                return ['status' => 'saved', 'name' => 'test_workflow'];
            }
        });
    }

    public function test_page_loads(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->assertSuccessful();
    }

    public function test_displays_step_palette(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->assertSee('Skill Execution')
            ->assertSee('Condition Check')
            ->assertSee('Delay')
            ->assertSee('Notification');
    }

    public function test_add_step(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->call('addStep', 'skill')
            ->assertSet('workflowSteps.0.type', 'skill');
    }

    public function test_remove_step(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->call('addStep', 'skill')
            ->call('addStep', 'notify')
            ->call('removeStep', 0)
            ->assertCount('workflowSteps', 1);
    }

    public function test_move_step_up(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->call('addStep', 'skill')
            ->call('addStep', 'notify')
            ->call('moveStepUp', 1)
            ->assertSet('workflowSteps.0.type', 'notify');
    }

    public function test_move_step_down(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->call('addStep', 'skill')
            ->call('addStep', 'notify')
            ->call('moveStepDown', 0)
            ->assertSet('workflowSteps.0.type', 'notify');
    }

    public function test_update_step_config(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->call('addStep', 'skill')
            ->call('updateStepConfig', 0, 'skill_name', 'server_health')
            ->assertSet('workflowSteps.0.config.skill_name', 'server_health');
    }

    public function test_generates_valid_yaml(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        $component = Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->set('workflowName', 'test_workflow')
            ->set('workflowDescription', 'A test workflow')
            ->call('addStep', 'skill')
            ->call('updateStepConfig', 0, 'skill_name', 'server_health')
            ->call('updateStepConfig', 0, 'description', 'Check health')
            ->call('generateYaml');

        $yaml = $component->get('generatedYaml');
        $this->assertNotEmpty($yaml);
        $this->assertStringContainsString('name: test_workflow', $yaml);
        $this->assertStringContainsString('server_health', $yaml);
    }

    public function test_save_workflow(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->set('workflowName', 'test_workflow')
            ->set('workflowDescription', 'A test workflow')
            ->call('addStep', 'skill')
            ->call('updateStepConfig', 0, 'skill_name', 'server_health')
            ->call('updateStepConfig', 0, 'description', 'Check health')
            ->call('saveWorkflow')
            ->assertHasNoErrors();
    }

    public function test_load_existing_workflow(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        $component = Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->call('loadWorkflow', 'daily_triage')
            ->assertSet('workflowName', 'daily_triage');

        $steps = $component->get('workflowSteps');
        $this->assertNotEmpty($steps);
    }

    public function test_navigation_registered(): void
    {
        $this->assertEquals('Skills Lab', WorkflowBuilder::getNavigationGroup());
        $this->assertEquals('heroicon-o-arrow-path', WorkflowBuilder::getNavigationIcon());
    }

    public function test_displays_existing_workflows(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->assertSee('daily_triage')
            ->assertSee('incident_response');
    }

    public function test_clear_builder(): void
    {
        $this->stubEngine();
        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(WorkflowBuilder::class)
            ->set('workflowName', 'test')
            ->call('addStep', 'skill')
            ->call('clearBuilder')
            ->assertSet('workflowName', '')
            ->assertSet('workflowSteps', []);
    }
}
