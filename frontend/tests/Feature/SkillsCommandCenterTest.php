<?php

namespace Tests\Feature;

use App\Filament\Pages\SkillsCommandCenter;
use App\Models\User;
use App\Services\SanaaEngineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class SkillsCommandCenterTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_merges_skill_metadata_and_prefills_arguments(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getSkillCatalog(bool $includeParameters = false): array
            {
                return [
                    'skills' => [
                        array_filter([
                            'name' => 'server_monitor',
                            'description' => 'Server monitor',
                            'version' => '1.0.0',
                            'category' => 'monitoring',
                            'tags' => ['infrastructure'],
                            'enabled' => true,
                            'requires_approval' => false,
                            'parameters' => $includeParameters ? [
                                'action' => [
                                    'type' => 'string',
                                    'description' => 'Action to run',
                                    'required' => true,
                                ],
                                'lines' => [
                                    'type' => 'integer',
                                    'description' => 'Lines to return',
                                    'required' => false,
                                    'default' => 50,
                                ],
                            ] : null,
                        ], static fn (mixed $value): bool => $value !== null),
                    ],
                    'tool_policy' => [],
                    'error' => '',
                ];
            }

            public function getSkillDefinition(string $skillName): ?array
            {
                return $this->getSkillCatalog(true)['skills'][0] ?? null;
            }
        });

        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(SkillsCommandCenter::class)
            ->assertSee('server_monitor')
            ->call('selectSkill', 'server_monitor')
            ->assertSet('selectedSkill.name', 'server_monitor')
            ->assertSet('skillArgs', "{\n    \"action\": \"\",\n    \"lines\": 50\n}");
    }

    public function test_it_runs_quick_actions_without_inline_json_directives(): void
    {
        $this->instance(SanaaEngineService::class, new class extends SanaaEngineService
        {
            public function __construct() {}

            public function getSkillCatalog(bool $includeParameters = false): array
            {
                return [
                    'skills' => [
                        array_filter([
                            'name' => 'session_logs',
                            'description' => 'Session logs',
                            'version' => '1.0.0',
                            'category' => 'system',
                            'tags' => [],
                            'enabled' => true,
                            'requires_approval' => false,
                            'parameters' => $includeParameters ? [
                                'action' => [
                                    'type' => 'string',
                                    'description' => 'Action to run',
                                    'required' => true,
                                ],
                                'limit' => [
                                    'type' => 'integer',
                                    'description' => 'Result limit',
                                    'required' => false,
                                    'default' => 20,
                                ],
                            ] : null,
                        ], static fn (mixed $value): bool => $value !== null),
                    ],
                    'tool_policy' => [],
                    'error' => '',
                ];
            }

            public function getSkillDefinition(string $skillName): ?array
            {
                return $this->getSkillCatalog(true)['skills'][0] ?? null;
            }

            public function runSkill(string $skillName, array $args = [], string $sessionId = '', int $timeout = 60): array
            {
                return [
                    'success' => true,
                    'output' => json_encode([
                        'skill' => $skillName,
                        'args' => $args,
                    ], JSON_UNESCAPED_SLASHES),
                ];
            }
        });

        $user = User::factory()->create();

        Livewire::actingAs($user)
            ->test(SkillsCommandCenter::class)
            ->call('runQuickAction', 'error_analysis')
            ->assertSet('selectedSkill.name', 'session_logs')
            ->assertSee('error_analysis')
            ->assertSee('session_logs');
    }
}
