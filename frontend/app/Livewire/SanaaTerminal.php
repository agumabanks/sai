<?php

namespace App\Livewire;

use App\Services\SanaaEngineService;
use Livewire\Component;

class SanaaTerminal extends Component
{
    public string $command = '';

    public array $history = [];

    public bool $isLoading = false;

    public ?string $pendingCommandId = null;

    /** @var string[] Ordered list of commands for up/down arrow navigation & localStorage persistence */
    public array $commandHistory = [];

    /** @var array<int, array{name: string, category: string}> Skill suggestions for autocomplete */
    public array $skillSuggestions = [];

    public function send()
    {
        if (empty(trim($this->command))) {
            return null;
        }

        $originalCommand = trim($this->command);
        $commandText = strtolower($originalCommand);

        // Track command in persistent history
        $this->commandHistory[] = $originalCommand;

        $this->history[] = [
            'type' => 'user',
            'text' => $this->command,
            'time' => now()->format('H:i'),
        ];
        $this->command = '';
        $this->isLoading = true;

        try {
            // Local commands (instant, no backend call)
            if ($this->handleLocalCommand($commandText, $originalCommand)) {
                return null;
            }

            // Run skill inline: "run skill <name>" or "skill <name>"
            if ($this->handleSkillCommand($originalCommand)) {
                return null;
            }

            // Everything else goes to the backend (async for AI, instant for intercepted commands)
            $engine = app(SanaaEngineService::class);
            $result = $engine->executeCommandAsync($originalCommand);

            if (isset($result['error'])) {
                $this->reply('❌ '.$result['error']);

                return null;
            }

            if (isset($result['id']) && ($result['status'] ?? '') === 'processing') {
                $this->pendingCommandId = $result['id'];
                $this->dispatch('command-sent');

                return null;
            }

            // Immediate response (scan, briefing, use brain, etc.)
            $this->reply($this->cleanAssistantResponse($result['response'] ?? $result['error'] ?? 'Command executed.'));
        } catch (\Exception $e) {
            $this->reply('❌ '.$e->getMessage());
        }

        return null;
    }

    public function pollCommand()
    {
        if (! $this->pendingCommandId) {
            return;
        }

        $engine = app(SanaaEngineService::class);
        $result = $engine->getCommandStatus($this->pendingCommandId);
        $status = $result['status'] ?? 'unknown';

        if ($status === 'completed' || $status === 'failed') {
            $response = $result['response'] ?? ($status === 'failed' ? '❌ Command failed' : '⚠️ No response');
            $this->reply($this->cleanAssistantResponse($response));
            $this->pendingCommandId = null;
        }
    }

    /**
     * Fetch skill names and categories for autocomplete suggestions.
     */
    public function getSkillNames(): void
    {
        try {
            $engine = app(SanaaEngineService::class);
            $catalog = $engine->getSkillCatalog();
            $skills = $catalog['skills'] ?? [];

            $this->skillSuggestions = array_map(
                fn (array $skill) => [
                    'name' => $skill['name'] ?? '',
                    'category' => $skill['category'] ?? 'system',
                ],
                $skills
            );
        } catch (\Exception $e) {
            $this->skillSuggestions = [];
        }
    }

    protected function handleLocalCommand(string $text, string $original): bool
    {
        // Shell command: prefix with ! or $
        if (preg_match('/^[!$]\s*(.+)$/', $original, $m)) {
            $this->runShellCommand(trim($m[1]));

            return true;
        }

        // Help
        if (in_array($text, ['help', '/help', '?', 'commands'])) {
            $this->reply($this->getHelpText());

            return true;
        }

        // Clear
        if (in_array($text, ['clear', '/clear'])) {
            $this->clearHistory();

            return true;
        }

        // Status
        if (in_array($text, ['status', '/status', 'system-check', 'check connection'])) {
            $this->runStatus();

            return true;
        }

        if ($this->looksLikeGroqStatusQuestion($text)) {
            $this->runGroqStatus();

            return true;
        }

        // List skills
        if (in_array($text, ['skills', '/skills', 'list skills'])) {
            $this->runListSkills();

            return true;
        }

        // Services
        if (in_array($text, ['services', '/services'])) {
            $this->runServices();

            return true;
        }

        // Alerts
        if (in_array($text, ['alerts', '/alerts'])) {
            $this->runAlerts();

            return true;
        }

        // Brain info or switch: "brain", "brain groq", "use brain groq"
        if (preg_match('/^(?:\/)?brain(?:\s+(\w+))?$/', $text, $m) || preg_match('/^use brain\s+(\w+)$/', $text, $m)) {
            $provider = $m[1] ?? null;
            if ($provider) {
                // Let the backend handle the switch
                return false;
            }
            $this->runBrainInfo();

            return true;
        }

        return false;
    }

    protected function handleSkillCommand(string $original): bool
    {
        // Match: "run skill <name> [args]", "skill <name> [args]", "run <name>"
        $pattern = '/^(?:run\s+)?skill\s+([a-z0-9_]+)(?:\s+(.+))?$/i';
        if (! preg_match($pattern, trim($original), $matches)) {
            // Also match: "run <known_skill_name>"
            $pattern2 = '/^run\s+([a-z0-9_]+)(?:\s+(.+))?$/i';
            if (! preg_match($pattern2, trim($original), $matches)) {
                return false;
            }
        }

        $skillName = strtolower(trim($matches[1] ?? ''));
        $argsText = trim($matches[2] ?? '');
        if ($skillName === '') {
            return false;
        }

        $args = [];
        if ($argsText !== '') {
            $decoded = json_decode($argsText, true);
            if (json_last_error() === JSON_ERROR_NONE && is_array($decoded)) {
                $args = $decoded;
            } else {
                $args = ['action' => $argsText];
            }
        }

        $engine = app(SanaaEngineService::class);

        try {
            $result = $engine->runSkill($skillName, $args, 'chat:terminal', 90);
        } catch (\Exception $e) {
            $this->reply("❌ Skill **{$skillName}** failed: ".$e->getMessage());

            return true;
        }

        $success = $result['success'] ?? false;
        $output = $result['output'] ?? $result['error'] ?? null;
        $data = $result['data'] ?? null;

        $response = $success ? '✅' : '❌';
        $response .= " **{$skillName}**\n\n";

        if ($output) {
            $response .= $output;
        } elseif ($data) {
            $response .= $this->formatSkillData($skillName, $data);
        } else {
            $response .= $success ? 'Completed successfully.' : 'Failed with no output.';
        }

        $this->reply($response);

        return true;
    }

    /**
     * Format skill result data as rich output.
     * Produces collapsible JSON sections and table formatting when possible.
     */
    protected function formatSkillData(string $skillName, mixed $data): string
    {
        if (! is_array($data)) {
            return (string) $data;
        }

        // Check if data looks like a table (array of uniform objects)
        if ($this->isTabular($data)) {
            return $this->formatAsTable($data);
        }

        // Format as pretty JSON code block with a label
        $json = json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);

        return "**Result data:**\n\n```json\n{$json}\n```";
    }

    /**
     * Check if an array looks like tabular data (list of objects with same keys).
     */
    protected function isTabular(array $data): bool
    {
        if (empty($data) || ! isset($data[0]) || ! is_array($data[0])) {
            return false;
        }

        $keys = array_keys($data[0]);
        if (empty($keys)) {
            return false;
        }

        // Check at least first 5 rows have the same keys
        foreach (array_slice($data, 0, 5) as $row) {
            if (! is_array($row) || array_keys($row) !== $keys) {
                return false;
            }
        }

        return true;
    }

    /**
     * Format tabular data as a markdown table.
     */
    protected function formatAsTable(array $data): string
    {
        if (empty($data) || ! is_array($data[0])) {
            return '';
        }

        $headers = array_keys($data[0]);
        $out = '| '.implode(' | ', $headers)." |\n";
        $out .= '|'.implode('|', array_fill(0, count($headers), '---'))."|\n";

        foreach ($data as $row) {
            $cells = array_map(function ($h) use ($row) {
                $val = $row[$h] ?? '';
                if (is_array($val)) {
                    return json_encode($val);
                }

                return (string) $val;
            }, $headers);
            $out .= '| '.implode(' | ', $cells)." |\n";
        }

        return $out;
    }

    protected function runStatus()
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();

        $server = $status['server'] ?? [];
        $cpu = $server['cpu']['percent'] ?? 0;
        $mem = $server['memory']['percent'] ?? 0;
        $disk = $server['disk']['percent'] ?? 0;
        $diskFree = round($server['disk']['free_gb'] ?? 0, 1);
        $provider = $status['channels']['active_provider'] ?? $status['brain']['active_provider'] ?? 'unknown';
        $overall = $server['overall_status'] ?? 'unknown';
        $services = $server['services'] ?? [];
        $activeServices = count(array_filter($services, fn ($s) => $s === 'active'));
        $totalServices = count($services);
        $alerts = $status['alerts']['unacknowledged'] ?? 0;
        $healer = ! empty($status['healer']['active_failures']);

        $icon = match ($overall) {
            'ok' => '🟢', 'warning' => '🟡', 'critical' => '🔴', default => '⚪'
        };

        $out = "## {$icon} System Status\n\n";
        $out .= "| Metric | Value |\n|---|---|\n";
        $out .= "| CPU | {$cpu}% |\n";
        $out .= "| Memory | {$mem}% |\n";
        $out .= "| Disk | {$disk}% ({$diskFree} GB free) |\n";
        $out .= "| Services | {$activeServices}/{$totalServices} active |\n";
        $out .= '| Brain | '.strtoupper($provider)." |\n";
        $out .= "| Alerts | {$alerts} unacknowledged |\n";
        $out .= '| Healer | '.($healer ? '🔴 Active recovery' : '🟢 Idle')." |\n";

        $this->reply($out);
    }

    protected function runListSkills()
    {
        $engine = app(SanaaEngineService::class);
        $catalog = $engine->getSkillCatalog();
        $skills = $catalog['skills'] ?? [];

        if (empty($skills)) {
            $this->reply('No skills found.');

            return;
        }

        $out = '## ⚡ Available Skills ('.count($skills).")\n\n";
        $out .= "| Skill | Category | Status |\n|---|---|---|\n";

        foreach ($skills as $skill) {
            $name = $skill['name'] ?? '';
            $cat = $skill['category'] ?? 'system';
            $enabled = ($skill['enabled'] ?? true) ? '🟢' : '⏸️';
            $out .= "| `{$name}` | {$cat} | {$enabled} |\n";
        }

        $out .= "\n**Usage:** `run skill <name>` or `run skill <name> {\"key\":\"value\"}`";

        $this->reply($out);
    }

    protected function runServices()
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();
        $services = $status['server']['services'] ?? [];

        if (empty($services)) {
            $this->reply('No services data available.');

            return;
        }

        $out = "## 🖥️ Services\n\n";
        $out .= "| Service | Status |\n|---|---|\n";

        foreach ($services as $name => $state) {
            $icon = $state === 'active' ? '🟢' : '🔴';
            $out .= "| {$name} | {$icon} {$state} |\n";
        }

        $this->reply($out);
    }

    protected function runAlerts()
    {
        $engine = app(SanaaEngineService::class);
        $alerts = $engine->getAlerts(10);

        if (empty($alerts)) {
            $this->reply('🛡️ **No active alerts.** All systems nominal.');

            return;
        }

        $out = "## 🔔 Recent Alerts\n\n";

        foreach (array_slice($alerts, 0, 8) as $alert) {
            $severity = strtoupper($alert['severity'] ?? 'INFO');
            $icon = match ($alert['severity'] ?? 'info') {
                'critical' => '🔴', 'high' => '🟠', 'warning' => '🟡', default => '🔵',
            };
            $msg = $alert['message'] ?? 'Unknown';
            $time = isset($alert['created_at']) ? \Carbon\Carbon::parse($alert['created_at'])->diffForHumans() : '';
            $out .= "{$icon} **{$severity}** — {$msg}";
            if ($time) {
                $out .= " *({$time})*";
            }
            $out .= "\n\n";
        }

        $this->reply($out);
    }

    protected function runBrainInfo()
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();
        $provider = $status['channels']['active_provider'] ?? $status['brain']['active_provider'] ?? 'unknown';

        $out = "## 🧠 Brain Configuration\n\n";
        $out .= '**Active Provider:** '.strtoupper($provider)."\n\n";
        $out .= "**Available provider:**\n";
        $out .= "- `groq` - Groq Cloud\n\n";
        $out .= '**Switch:** `use brain groq`';

        $this->reply($out);
    }

    protected function runGroqStatus(): void
    {
        $engine = app(SanaaEngineService::class);
        $status = $engine->getStatus();
        $provider = strtolower((string) ($status['channels']['active_provider'] ?? $status['brain']['active_provider'] ?? 'unknown'));
        $model = $status['channels']['active_model'] ?? $status['brain']['active_model'] ?? 'llama-3.1-8b-instant';

        if ($provider === 'groq') {
            $this->reply("Yes. Groq is active and powering Sanaa Chat right now.\n\n**Model:** `{$model}`\n\nOllama, Claude, and OpenRouter are not being used from this dashboard.");

            return;
        }

        $this->reply("Groq is configured as the intended provider, but the backend is currently reporting `{$provider}`.\n\nUse `brain` or refresh the dashboard after the provider switch finishes.");
    }

    protected function looksLikeGroqStatusQuestion(string $text): bool
    {
        if (! str_contains($text, 'groq')) {
            return false;
        }

        return str_contains($text, ' on')
            || str_contains($text, 'online')
            || str_contains($text, 'working')
            || str_contains($text, 'active')
            || str_contains($text, 'available')
            || str_contains($text, 'running')
            || str_contains($text, 'status')
            || str_contains($text, '?');
    }

    protected function cleanAssistantResponse(string $text): string
    {
        $text = trim($text);

        if ($text === '') {
            return 'No response came back from Sanaa AI.';
        }

        $lines = preg_split('/\R/', $text) ?: [];
        $cleaned = [];

        foreach ($lines as $line) {
            $line = trim($line);

            if ($line === '' || preg_match('/^(USER|ASSISTANT)\s*:/i', $line)) {
                continue;
            }

            $cleaned[] = $line;
        }

        return trim(implode("\n", $cleaned)) ?: $text;
    }

    protected function runShellCommand(string $cmd): void
    {
        $user = auth()->user();
        if ($user && method_exists($user, 'isViewer') && $user->isViewer()) {
            $this->reply('🚫 **Blocked:** Viewer accounts cannot execute shell commands.');

            return;
        }

        $engine = app(SanaaEngineService::class);

        try {
            $result = $engine->executeTerminal($cmd, null);
        } catch (\Exception $e) {
            $this->reply('❌ Terminal error: '.$e->getMessage());

            return;
        }

        if (! ($result['success'] ?? false)) {
            $this->reply('🚫 **Blocked:** '.($result['error'] ?? 'Command failed'));

            return;
        }

        $stdout = (string) ($result['stdout'] ?? '');
        $stderr = (string) ($result['stderr'] ?? '');
        $returncode = (int) ($result['returncode'] ?? 0);

        $output = '';
        if ($stdout !== '') {
            $output .= "```\n".rtrim($stdout)."\n```\n";
        }
        if ($stderr !== '') {
            $output .= "**stderr:**\n```\n".rtrim($stderr)."\n```\n";
        }
        if ($returncode !== 0) {
            $output .= "Exit code: {$returncode}";
        }

        $this->reply($output !== '' ? trim($output) : '✅ Command completed with no output.');
    }

    protected function getHelpText(): string
    {
        return "## Sanaa Chat - Commands\n\n".
            "### System\n".
            "| Command | Description |\n|---|---|\n".
            "| `status` | System health, CPU, memory, services |\n".
            "| `services` | Service status (nginx, redis, etc.) |\n".
            "| `alerts` | Recent watchdog alerts |\n".
            "| `brain` | Show brain configuration |\n".
            "| `use brain <provider>` | Switch AI provider |\n\n".
            "### Skills\n".
            "| Command | Description |\n|---|---|\n".
            "| `skills` | List all available skills |\n".
            "| `run skill <name>` | Execute any skill |\n".
            "| `skill <name>` | Shorthand skill execution |\n".
            "| `run <name>` | Run a skill by name |\n".
            "| `run skill <name> {\"key\":\"val\"}` | Execute with JSON args |\n\n".
            "### Shell (admin)\n".
            "| Command | Description |\n|---|---|\n".
            "| `! <command>` | Full server shell (admin) |\n".
            "| `$ <command>` | Alias for shell execution |\n\n".
            "### Actions\n".
            "| Command | Description |\n|---|---|\n".
            "| `scan` | Run security audit |\n".
            "| `briefing` | Generate intelligence briefing |\n".
            "| `clear` | Clear chat history |\n\n".
            "### Shell (prefix with `!` or `\$`)\n".
            "| Command | Example |\n|---|---|\n".
            "| `! <command>` | `! df -h` |\n".
            "| `! docker ps` | List running containers |\n".
            "| `! systemctl status nginx` | Check service |\n".
            "| `! tail -20 /var/log/syslog` | Read logs |\n".
            "| `! droid --help` | Run any CLI tool |\n\n".
            "**Tips:** Use the up/down arrows to navigate command history. Type `run skill` for autocomplete.\n\n".
            'Or just type naturally - Sanaa AI will respond using **Groq only**.';
    }

    protected function reply(string $text): void
    {
        $this->history[] = [
            'type' => 'ai',
            'text' => $text,
            'time' => now()->format('H:i'),
        ];
        $this->isLoading = false;
        $this->dispatch('command-sent');
    }

    public function clearHistory(): void
    {
        $this->history = [];
        $this->pendingCommandId = null;
        $this->isLoading = false;
        // Note: commandHistory is preserved for localStorage persistence
    }

    public function render()
    {
        return view('livewire.sanaa-terminal');
    }
}
