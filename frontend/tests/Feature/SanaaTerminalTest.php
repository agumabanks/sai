<?php

namespace Tests\Feature;

use App\Livewire\SanaaTerminal;
use App\Services\SanaaEngineService;
use Livewire\Livewire;
use Mockery;
use Tests\TestCase;

class SanaaTerminalTest extends TestCase
{
    // ── Existing functionality ───────────────────────────────────────────

    public function test_help_command_returns_command_list(): void
    {
        Livewire::test(SanaaTerminal::class)
            ->set('command', 'help')
            ->call('send')
            ->assertSet('isLoading', false)
            ->assertSee('Sanaa Neural Link');
    }

    public function test_status_command_returns_system_info(): void
    {
        Livewire::test(SanaaTerminal::class)
            ->set('command', 'status')
            ->call('send')
            ->assertSet('isLoading', false);
    }

    public function test_clear_command_resets_history(): void
    {
        Livewire::test(SanaaTerminal::class)
            ->set('command', 'help')
            ->call('send')
            ->set('command', 'clear')
            ->call('send')
            ->assertSet('history', []);
    }

    public function test_skill_command_runs_inline(): void
    {
        Livewire::test(SanaaTerminal::class)
            ->set('command', 'run skill healthcheck')
            ->call('send')
            ->assertSet('isLoading', false)
            ->assertNoRedirect();
    }

    public function test_shell_command_executes(): void
    {
        Livewire::test(SanaaTerminal::class)
            ->set('command', '! echo hello_from_shell')
            ->call('send')
            ->assertSet('isLoading', false)
            ->assertSee('hello_from_shell');
    }

    public function test_shell_blocks_destructive_commands(): void
    {
        Livewire::test(SanaaTerminal::class)
            ->set('command', '! rm -rf /')
            ->call('send')
            ->assertSee('Blocked');
    }

    // ── Command history persistence ─────────────────────────────────────

    public function test_terminal_has_command_history_property(): void
    {
        $component = Livewire::test(SanaaTerminal::class);

        // The component should have a commandHistory property (array of past commands)
        $component->assertSet('commandHistory', []);
    }

    public function test_command_history_populated_after_send(): void
    {
        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', 'help')
            ->call('send');

        // After sending a command, it should appear in commandHistory
        $history = $component->get('commandHistory');
        $this->assertIsArray($history);
        $this->assertContains('help', $history);
    }

    public function test_command_history_accumulates_multiple_commands(): void
    {
        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', 'help')
            ->call('send')
            ->set('command', 'status')
            ->call('send')
            ->set('command', 'skills')
            ->call('send');

        $history = $component->get('commandHistory');
        $this->assertCount(3, $history);
        $this->assertEquals(['help', 'status', 'skills'], $history);
    }

    public function test_clear_does_not_erase_command_history(): void
    {
        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', 'help')
            ->call('send')
            ->set('command', 'clear')
            ->call('send');

        // Clear should clear display history but preserve command history for persistence
        $commandHistory = $component->get('commandHistory');
        $this->assertContains('help', $commandHistory);
    }

    public function test_empty_commands_not_added_to_history(): void
    {
        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', '')
            ->call('send')
            ->set('command', '   ')
            ->call('send');

        $history = $component->get('commandHistory');
        $this->assertEmpty($history);
    }

    public function test_terminal_history_persistence(): void
    {
        // VAL-UI-006: Test that the component exposes commandHistory
        // so Alpine.js can persist it to localStorage
        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', 'help')
            ->call('send')
            ->set('command', 'status')
            ->call('send');

        $commandHistory = $component->get('commandHistory');
        $this->assertIsArray($commandHistory);
        $this->assertCount(2, $commandHistory);
        $this->assertEquals('help', $commandHistory[0]);
        $this->assertEquals('status', $commandHistory[1]);
    }

    // ── Rich output rendering ───────────────────────────────────────────

    public function test_terminal_rich_output(): void
    {
        // VAL-UI-006: Test that skill results with JSON data get rich formatting
        $mockEngine = Mockery::mock(SanaaEngineService::class);
        $mockEngine->shouldReceive('runSkill')
            ->once()
            ->andReturn([
                'success' => true,
                'output' => null,
                'data' => ['key' => 'value', 'nested' => ['a' => 1]],
            ]);

        $this->app->instance(SanaaEngineService::class, $mockEngine);

        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', 'run skill test_skill')
            ->call('send');

        // The history should contain formatted JSON output
        $history = $component->get('history');
        $lastAiMessage = collect($history)->where('type', 'ai')->last();
        $this->assertNotNull($lastAiMessage);
        $this->assertStringContainsString('test_skill', $lastAiMessage['text']);
    }

    public function test_skill_output_with_json_data_renders_formatted(): void
    {
        $mockEngine = Mockery::mock(SanaaEngineService::class);
        $mockEngine->shouldReceive('runSkill')
            ->once()
            ->andReturn([
                'success' => true,
                'output' => null,
                'data' => ['status' => 'ok', 'count' => 42],
            ]);

        $this->app->instance(SanaaEngineService::class, $mockEngine);

        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', 'run skill analytics')
            ->call('send');

        $history = $component->get('history');
        $aiMessages = collect($history)->where('type', 'ai');
        $lastMsg = $aiMessages->last();

        // JSON data should be in the response
        $this->assertStringContainsString('status', $lastMsg['text']);
        $this->assertStringContainsString('ok', $lastMsg['text']);
    }

    public function test_table_output_renders_properly(): void
    {
        // Test that markdown tables in output are present
        $component = Livewire::test(SanaaTerminal::class)
            ->set('command', 'help')
            ->call('send');

        $history = $component->get('history');
        $aiMsg = collect($history)->where('type', 'ai')->last();

        // Help output contains markdown tables
        $this->assertStringContainsString('|', $aiMsg['text']);
        $this->assertStringContainsString('Command', $aiMsg['text']);
    }

    // ── Skill suggestions/autocomplete ──────────────────────────────────

    public function test_skill_suggestions_property_exists(): void
    {
        $component = Livewire::test(SanaaTerminal::class);
        $component->assertSet('skillSuggestions', []);
    }

    public function test_get_skill_names_returns_array(): void
    {
        $component = Livewire::test(SanaaTerminal::class);
        $result = $component->call('getSkillNames');

        $names = $component->get('skillSuggestions');
        $this->assertIsArray($names);
    }

    public function test_update_suggestions_triggered_by_run_skill(): void
    {
        $mockEngine = Mockery::mock(SanaaEngineService::class);
        $mockEngine->shouldReceive('getSkillCatalog')
            ->andReturn([
                'skills' => [
                    ['name' => 'healthcheck', 'category' => 'monitoring'],
                    ['name' => 'scanner', 'category' => 'security'],
                    ['name' => 'briefing', 'category' => 'research'],
                ],
            ]);

        $this->app->instance(SanaaEngineService::class, $mockEngine);

        $component = Livewire::test(SanaaTerminal::class)
            ->call('getSkillNames');

        $suggestions = $component->get('skillSuggestions');
        $this->assertNotEmpty($suggestions);
    }

    public function test_skill_suggestions_contain_name_and_category(): void
    {
        $mockEngine = Mockery::mock(SanaaEngineService::class);
        $mockEngine->shouldReceive('getSkillCatalog')
            ->andReturn([
                'skills' => [
                    ['name' => 'healthcheck', 'category' => 'monitoring'],
                    ['name' => 'scanner', 'category' => 'security'],
                ],
            ]);

        $this->app->instance(SanaaEngineService::class, $mockEngine);

        $component = Livewire::test(SanaaTerminal::class)
            ->call('getSkillNames');

        $suggestions = $component->get('skillSuggestions');
        $this->assertNotEmpty($suggestions);

        $first = $suggestions[0];
        $this->assertArrayHasKey('name', $first);
        $this->assertArrayHasKey('category', $first);
    }
}
