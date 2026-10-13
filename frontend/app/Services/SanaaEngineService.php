<?php

namespace App\Services;

use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class SanaaEngineService
{
    protected string $baseUrl;

    protected string $apiKey;

    protected ?string $lastError = null;

    public function __construct()
    {
        // Internal proxy to the Python backend
        $this->baseUrl = config('services.sanaa_engine.url', 'http://127.0.0.1:8100/api');
        $this->apiKey = config('services.sanaa_engine.key', '');
    }

    /**
     * HTTP client with authenticated actor context for the Python backend.
     */
    protected function client(int $timeout = 30): \Illuminate\Http\Client\PendingRequest
    {
        $client = Http::withToken($this->apiKey)->timeout($timeout)->acceptJson();

        if (auth()->check()) {
            $user = auth()->user();
            $client = $client->withHeaders([
                'X-Sanaa-User' => (string) $user->email,
                'X-Sanaa-Role' => (string) ($user->role ?? 'operator'),
                'X-Sanaa-Name' => (string) ($user->name ?? $user->email),
            ]);
        }

        return $client;
    }

    /**
     * Execute a shell command through the secured backend terminal API.
     */
    public function executeTerminal(string $command, ?string $cwd = null): array
    {
        try {
            $response = $this->client(190)->post("{$this->baseUrl}/terminal/exec", array_filter([
                'command' => $command,
                'cwd' => $cwd ?? '/var/www/ai.sanaa.co',
            ], fn ($value) => $value !== null));

            if ($response->failed()) {
                $detail = $response->json('detail', $response->body());

                return [
                    'success' => false,
                    'error' => is_string($detail) ? $detail : json_encode($detail),
                    'returncode' => 1,
                ];
            }

            return array_merge($response->json() ?? [], ['success' => true]);
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Terminal Error: '.$e->getMessage());

            return ['success' => false, 'error' => $e->getMessage(), 'returncode' => 1];
        }
    }

    /**
     * Get the current system status.
     */
    public function getStatus(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->get("{$this->baseUrl}/status");

            if ($response->failed()) {
                $message = $this->buildHttpFailureMessage('status', $response);
                $this->recordError('Sanaa Engine Status Failed', $message, $response);

                return ['status' => 'offline', 'error' => $message];
            }

            $payload = $response->json();
            if (! is_array($payload) || array_is_list($payload)) {
                $message = 'Sanaa Engine returned an unexpected status payload. Verify the backend port mapping and API credentials.';
                $this->recordError('Sanaa Engine Status Payload Error', $message, $response);

                return ['status' => 'offline', 'error' => $message];
            }

            return $payload;
        } catch (\Exception $e) {
            $message = 'Sanaa Engine status request failed: '.$e->getMessage();
            $this->recordError('Sanaa Engine Status Error', $message);

            return ['status' => 'offline', 'error' => $message];
        }
    }

    public function clearLastError(): void
    {
        $this->lastError = null;
    }

    public function getLastError(): ?string
    {
        return $this->lastError;
    }

    protected function buildHttpFailureMessage(string $endpoint, Response $response): string
    {
        $details = trim((string) $response->json('error', $response->json('detail', '')));
        $suffix = $details !== '' ? " ({$details})" : '';

        return "Sanaa Engine {$endpoint} request returned HTTP {$response->status()}{$suffix}. Verify SANAA_ENGINE_URL, Nginx /api proxy, and the antigravity-web service port.";
    }

    protected function recordError(string $logContext, string $message, ?Response $response = null): void
    {
        $this->lastError = $message;

        Log::warning($logContext, array_filter([
            'message' => $message,
            'status' => $response?->status(),
            'body' => $response?->body(),
            'base_url' => $this->baseUrl,
        ], fn ($value) => $value !== null));
    }

    /**
     * Execute a command.
     */
    public function executeCommand(string $command): array
    {
        try {
            $response = $this->client(120)->post("{$this->baseUrl}/command", [
                'command' => $command,
            ]);

            if ($response->failed()) {
                Log::error('Sanaa Engine Command Failed', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);

                return [
                    'error' => 'Backend returned error: '.$response->status(),
                    'status' => 'failed',
                ];
            }

            return $response->json() ?? ['error' => 'Invalid response format'];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Command Error: '.$e->getMessage());

            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    public function executeCommandAsync(string $command): array
    {
        try {
            $response = $this->client(10)->post("{$this->baseUrl}/command", [
                'command' => $command,
                'async' => true,
            ]);

            return $response->json() ?? ['error' => 'Invalid response'];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Async Command Error: '.$e->getMessage());

            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    public function getCommandStatus(string $cmdId): array
    {
        try {
            $response = $this->client(5)->get("{$this->baseUrl}/command/{$cmdId}");

            return $response->json() ?? ['status' => 'unknown'];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Command Status Error: '.$e->getMessage());

            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    /**
     * Set the LLM provider.
     */
    public function setProvider(string $provider): bool
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->post("{$this->baseUrl}/system/brain/provider", [
                    'provider' => $provider,
                ]);

            if ($response->successful()) {
                Log::info('Brain provider switched', ['provider' => $provider]);

                return true;
            }

            Log::error('Failed to switch brain provider', [
                'provider' => $provider,
                'status' => $response->status(),
                'body' => $response->body(),
            ]);

            return false;
        } catch (\Exception $e) {
            Log::error('Brain provider switch error', [
                'provider' => $provider,
                'error' => $e->getMessage(),
            ]);

            return false;
        }
    }

    /**
     * Get editable AI brain configuration.
     */
    public function getBrainConfig(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/system/brain/config");

            if ($response->failed()) {
                Log::error('Failed to fetch brain config', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);

                return [];
            }

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Brain config fetch error', ['error' => $e->getMessage()]);

            return [];
        }
    }

    /**
     * Update AI brain configuration.
     */
    public function updateBrainConfig(array $payload): bool
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(20)
                ->post("{$this->baseUrl}/system/brain/config", $payload);

            if ($response->successful()) {
                return true;
            }

            Log::error('Failed to update brain config', [
                'status' => $response->status(),
                'body' => $response->body(),
                'payload_keys' => array_keys($payload),
            ]);

            return false;
        } catch (\Exception $e) {
            Log::error('Brain config update error', ['error' => $e->getMessage()]);

            return false;
        }
    }

    /**
     * Get recent system activities for the dashboard feed.
     */
    public function getActivities(int $limit = 20): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/activities", [
                    'limit' => $limit,
                ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Activities Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get recent intelligence briefings.
     */
    public function getBriefings(int $limit = 20): array
    {
        try {
            $response = Http::withToken($this->apiKey)->get("{$this->baseUrl}/intelligence/briefings", [
                'limit' => $limit,
            ]);

            if ($response->failed()) {
                $this->recordError(
                    'Sanaa Engine Briefings Failed',
                    $this->buildHttpFailureMessage('briefings', $response),
                    $response,
                );

                return [];
            }

            $payload = $response->json();
            if (! is_array($payload) || ! array_is_list($payload)) {
                $message = 'Sanaa Engine briefings response was not a list. Verify the backend route and proxy target before using the dashboard.';
                $this->recordError('Sanaa Engine Briefings Payload Error', $message, $response);

                return [];
            }

            return $payload;
        } catch (\Exception $e) {
            $this->recordError('Sanaa Engine Briefings Error', 'Sanaa Engine briefings request failed: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get a specific intelligence briefing.
     */
    public function getBriefing(int $id): array
    {
        try {
            $response = Http::withToken($this->apiKey)->get("{$this->baseUrl}/intelligence/briefing/{$id}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Briefing Detail Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get the latest strategic signal.
     */
    public function getLatestSignal(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->get("{$this->baseUrl}/intelligence/latest-signal");

            if ($response->failed()) {
                $this->recordError(
                    'Sanaa Engine Latest Signal Failed',
                    $this->buildHttpFailureMessage('latest-signal', $response),
                    $response,
                );

                return ['status' => 'none'];
            }

            $payload = $response->json();
            if (! is_array($payload) || array_is_list($payload)) {
                $message = 'Sanaa Engine latest signal response was invalid. Verify the backend route and proxy target before using the dashboard.';
                $this->recordError('Sanaa Engine Latest Signal Payload Error', $message, $response);

                return ['status' => 'none'];
            }

            return $payload;
        } catch (\Exception $e) {
            $this->recordError('Sanaa Engine Signal Error', 'Sanaa Engine latest-signal request failed: '.$e->getMessage());

            return ['status' => 'none'];
        }
    }

    /**
     * Get recent strategic signals (market opportunities/threats).
     */
    public function getStrategicSignals(int $limit = 10): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/intelligence/latest-signals", ['limit' => $limit]);
            $data = $response->json();

            // Ensure we return a list of items, not an associative error object
            return (is_array($data) && (! empty($data) ? array_is_list($data) : true)) ? $data : [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Signals Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get the latest architectural wisdom/insight from the system.
     */
    public function getSystemWisdom(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/intelligence/wisdom");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Wisdom Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get recent alerts.
     */
    public function getAlerts(int $limit = 10): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/alerts", ['limit' => $limit]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Alerts Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Update a system preference.
     */
    public function updatePreference(string $key, $value): bool
    {
        try {
            $response = Http::withToken($this->apiKey)->post("{$this->baseUrl}/system/preference", [
                'key' => $key,
                'value' => $value,
            ]);

            return $response->successful();
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Preference Error: '.$e->getMessage());

            return false;
        }
    }

    /**
     * Get system preferences.
     */
    public function getPreferences(array $keys): array
    {
        try {
            $keysStr = implode(',', $keys);
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/system/preferences", [
                'keys' => $keysStr,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Get Preferences Error: '.$e->getMessage());

            return [];
        }
    }

    public function getToolPolicy(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/system/tool-policy");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Tool Policy Error: '.$e->getMessage());

            return [];
        }
    }

    public function updateToolPolicy(array $payload): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->post("{$this->baseUrl}/system/tool-policy", $payload);

            return $response->json() ?? ['status' => 'failed'];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Tool Policy Update Error: '.$e->getMessage());

            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    public function getSkills(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Skills Error: '.$e->getMessage());

            return [];
        }
    }

    public function getSkillCatalog(bool $includeParameters = false): array
    {
        $payload = $this->getSkills();

        if (! is_array($payload)) {
            return [
                'skills' => [],
                'tool_policy' => [],
                'error' => 'Invalid skills payload returned by the Sanaa engine.',
            ];
        }

        $toolIndex = [];

        foreach ($payload['tools'] ?? [] as $tool) {
            $function = $tool['function'] ?? null;

            if (! is_array($function)) {
                continue;
            }

            $name = (string) ($function['name'] ?? '');

            if ($name === '') {
                continue;
            }

            $schema = is_array($function['parameters'] ?? null)
                ? $function['parameters']
                : [];

            $toolIndex[$name] = [
                'parameters' => $this->normalizeSkillParameters($schema),
            ];
        }

        $skills = [];

        foreach ($payload['skills'] ?? [] as $skill) {
            if (! is_array($skill)) {
                continue;
            }

            $name = (string) ($skill['name'] ?? '');

            if ($name === '') {
                continue;
            }

            $groups = $this->normalizeStringList($skill['groups'] ?? []);
            $tags = $this->normalizeStringList($skill['tags'] ?? []);
            $category = $this->resolveSkillCategory($groups, $tags);

            $entry = [
                'name' => $name,
                'description' => (string) ($skill['description'] ?? ''),
                'version' => (string) ($skill['version'] ?? '1.0.0'),
                'category' => $category,
                'tags' => $tags,
                'enabled' => ($skill['enabled'] ?? true) !== false,
                'requires_approval' => (bool) ($skill['requires_approval'] ?? false),
            ];

            if ($includeParameters) {
                $entry['parameters'] = $toolIndex[$name]['parameters'] ?? [];
            }

            $skills[] = $entry;
        }

        usort($skills, fn (array $left, array $right): int => strcmp($left['name'], $right['name']));

        return [
            'skills' => $skills,
            'tool_policy' => is_array($payload['tool_policy'] ?? null) ? $payload['tool_policy'] : [],
            'error' => (string) ($payload['error'] ?? ''),
        ];
    }

    public function getSkillDefinition(string $skillName): ?array
    {
        foreach ($this->getSkillCatalog(true)['skills'] as $skill) {
            if (($skill['name'] ?? '') === $skillName) {
                return $skill;
            }
        }

        return null;
    }

    public function setSkillEnabled(string $skill, bool $enabled): array
    {
        $endpoint = $enabled ? 'enable' : 'disable';
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/skills/{$skill}/{$endpoint}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Skill Toggle Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function setSkillExposure(string $skill, string $exposure): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/skills/{$skill}/exposure", [
                'exposure' => $exposure,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Skill Exposure Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Run a specific skill with the given arguments.
     */
    public function runSkill(string $skillName, array $args = [], string $sessionId = '', int $timeout = 120): array
    {
        try {
            $response = $this->client($timeout)->post("{$this->baseUrl}/skills/{$skillName}/run", [
                'args' => $args,
                'session_id' => $sessionId ?: 'admin:skills_center',
            ]);
            $json = $response->json() ?? [];

            // The backend wraps skill results in 'detail' on 400 responses
            // (when success=false, e.g. alerts found). Extract the actual data.
            if ($response->failed() && isset($json['detail']) && is_array($json['detail'])) {
                return $json['detail'];
            }
            if ($response->failed()) {
                return ['success' => false, 'error' => 'HTTP '.$response->status().': '.$response->body()];
            }

            return $json ?: ['success' => false, 'error' => 'Empty response'];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Skill Run Error: '.$e->getMessage());

            return ['success' => false, 'error' => $e->getMessage()];
        }
    }

    /**
     * Get recent skill run history (via session_logs tool_calls).
     */
    public function getSkillRuns(int $limit = 20): array
    {
        return $this->runSkill('session_logs', ['action' => 'tool_calls', 'limit' => $limit]);
    }

    /**
     * Hot-reload a skill into the live registry.
     */
    public function hotReloadSkill(string $skillName): array
    {
        return $this->runSkill('skill_creator', ['action' => 'hot_reload', 'skill_name' => $skillName]);
    }

    /**
     * Create a new skill from a natural language description.
     */
    public function createSkill(string $skillName, string $description): array
    {
        return $this->runSkill('skill_creator', [
            'action' => 'create',
            'skill_name' => $skillName,
            'skill_description' => $description,
        ]);
    }

    public function getWorkflows(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/workflows");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflows Error: '.$e->getMessage());

            return [];
        }
    }

    public function getWorkflowRuns(int $limit = 50): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/workflows/runs", ['limit' => $limit]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflow Runs Error: '.$e->getMessage());

            return [];
        }
    }

    public function runWorkflow(string $workflowName, array $args = []): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(20)->post("{$this->baseUrl}/workflows/{$workflowName}/run", [
                'args' => $args,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflow Start Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function getWorkflowRun(int $runId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/workflows/runs/{$runId}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflow Run Error: '.$e->getMessage());

            return [];
        }
    }

    public function getWorkflowApproval(int $runId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/workflows/runs/{$runId}/approval");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflow Approval Error: '.$e->getMessage());

            return [];
        }
    }

    public function resumeWorkflowRun(int $runId, bool $approved, string $resumeToken): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(20)->post("{$this->baseUrl}/workflows/runs/{$runId}/resume", [
                'approved' => $approved,
                'resume_token' => $resumeToken,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflow Resume Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function cancelWorkflowRun(int $runId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/workflows/runs/{$runId}/cancel");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflow Cancel Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Save a workflow definition from YAML content.
     * Posts the YAML body to the backend which writes it to the workflows directory.
     */
    public function saveWorkflow(string $yaml): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->withBody($yaml, 'application/x-yaml')
                ->post("{$this->baseUrl}/workflows");

            return $response->json() ?? ['status' => 'saved'];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Workflow Save Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function getSessionPolicy(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/system/session-policy");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Session Policy Error: '.$e->getMessage());

            return [];
        }
    }

    public function updateSessionPolicy(array $payload): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->post("{$this->baseUrl}/system/session-policy", $payload);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Session Policy Update Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    protected function normalizeSkillParameters(array $schema): array
    {
        $properties = is_array($schema['properties'] ?? null)
            ? $schema['properties']
            : [];
        $required = array_fill_keys(
            array_values(array_filter($schema['required'] ?? [], 'is_string')),
            true,
        );

        $normalized = [];

        foreach ($properties as $name => $definition) {
            if (! is_string($name) || ! is_array($definition)) {
                continue;
            }

            $normalized[$name] = [
                'type' => (string) ($definition['type'] ?? 'string'),
                'description' => (string) ($definition['description'] ?? ''),
                'required' => isset($required[$name]),
                'default' => $definition['default'] ?? null,
                'enum' => $this->normalizeStringList($definition['enum'] ?? []),
            ];
        }

        return $normalized;
    }

    protected function normalizeStringList(mixed $values): array
    {
        if (! is_array($values)) {
            return [];
        }

        return array_values(array_filter(
            array_map(
                static fn (mixed $value): string => is_string($value) ? trim($value) : '',
                $values,
            ),
            static fn (string $value): bool => $value !== '',
        ));
    }

    protected function resolveSkillCategory(array $groups, array $tags): string
    {
        $candidates = array_map('strtolower', array_merge($groups, $tags));

        foreach ($candidates as $candidate) {
            if (in_array($candidate, ['development', 'coding', 'developer'], true)) {
                return 'development';
            }

            if (in_array($candidate, ['monitoring', 'operations', 'infrastructure', 'finance', 'server'], true)) {
                return 'monitoring';
            }

            if (in_array($candidate, ['communication', 'whatsapp', 'telegram', 'email'], true)) {
                return 'communication';
            }

            if (in_array($candidate, ['productivity', 'workflow', 'project', 'tasks'], true)) {
                return 'productivity';
            }

            if (in_array($candidate, ['research', 'news', 'analysis'], true)) {
                return 'research';
            }

            if (in_array($candidate, ['meta', 'ai', 'brain', 'reflection'], true)) {
                return 'meta';
            }
        }

        return 'system';
    }

    // ── ML Self-Learning API ──────────────────────────────────────────────

    public function getMLScores(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills/ml/scores");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Scores Error: '.$e->getMessage());

            return [];
        }
    }

    public function getSkillMLScore(string $skillName): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills/{$skillName}/ml/score");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Skill Score Error: '.$e->getMessage());

            return [];
        }
    }

    public function getSkillMLMetrics(string $skillName, string $period = 'daily', int $limit = 30): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills/{$skillName}/ml/metrics", [
                'period' => $period,
                'limit' => $limit,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Metrics Error: '.$e->getMessage());

            return [];
        }
    }

    public function submitSkillFeedback(string $skillName, int $rating, string $type = 'thumbs', ?string $comment = null, ?int $runId = null): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/skills/{$skillName}/ml/feedback", [
                'rating' => $rating,
                'feedback_type' => $type,
                'comment' => $comment,
                'skill_run_id' => $runId,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Feedback Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function getSkillLearningLog(string $skillName, int $limit = 20): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/skills/{$skillName}/ml/learning", [
                'limit' => $limit,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Learning Log Error: '.$e->getMessage());

            return [];
        }
    }

    public function getSkillParameterInsights(string $skillName): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills/{$skillName}/ml/parameters");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Parameters Error: '.$e->getMessage());

            return [];
        }
    }

    public function triggerMLAnalysis(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(60)->post("{$this->baseUrl}/skills/ml/analyze");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Analysis Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function getGlobalLearningLog(int $limit = 50): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/skills/ml/learning-log", [
                'limit' => $limit,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa ML Global Learning Log Error: '.$e->getMessage());

            return [];
        }
    }

    public function getSessions(int $limit = 100): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/sessions", ['limit' => $limit]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Sessions Error: '.$e->getMessage());

            return [];
        }
    }

    public function getSessionDetail(string $sessionId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/sessions/{$sessionId}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Session Detail Error: '.$e->getMessage());

            return [];
        }
    }

    public function resetSession(string $sessionId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/sessions/{$sessionId}/reset");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Session Reset Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function setSessionSendPolicy(string $sessionId, string $mode): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/sessions/{$sessionId}/send-policy", [
                'mode' => $mode,
            ]);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Session Send Policy Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    public function getDoctorReport(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(20)->get("{$this->baseUrl}/system/doctor");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Doctor Error: '.$e->getMessage());

            return [];
        }
    }

    public function getWatchdogAdvisor(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/intelligence/advisor/watchdog");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Watchdog Advisor Error: '.$e->getMessage());

            return [];
        }
    }

    public function getLatestBriefingQa(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/intelligence/briefings/qa/latest");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Briefing QA Error: '.$e->getMessage());

            return [];
        }
    }

    // ── Marketing Dashboard API ──────────────────────────────────────────

    /**
     * Get aggregated marketing metrics (campaigns, email stats, social stats).
     */
    public function getMarketingMetrics(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/marketing/metrics");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Marketing Metrics Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get social media analytics overview (post counts, platform breakdown, recent posts).
     */
    public function getSocialAnalytics(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/marketing/social");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Social Analytics Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get scheduled content calendar (upcoming posts and campaign tasks).
     */
    public function getScheduledContent(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/marketing/calendar");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Scheduled Content Error: '.$e->getMessage());

            return [];
        }
    }

    // ── Memory & Learning Logs API ────────────────────────────────────────

    /**
     * Get stored memories with optional search and category filter.
     */
    public function getMemories(?string $search = null, ?string $category = null, int $limit = 50): array
    {
        try {
            $params = ['limit' => $limit];
            if ($search !== null && $search !== '') {
                $params['search'] = $search;
            }
            if ($category !== null && $category !== '') {
                $params['category'] = $category;
            }
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/memories", $params);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Memories Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get learning log entries with optional type filter.
     */
    public function getLearningLogs(?string $type = null, int $limit = 50): array
    {
        try {
            $params = ['limit' => $limit];
            if ($type !== null && $type !== '') {
                $params['log_type'] = $type;
            }
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/learning-logs", $params);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Learning Logs Error: '.$e->getMessage());

            return [];
        }
    }

    // ── Tenant Control API ────────────────────────────────────────────────

    /**
     * List all registered tenants.
     */
    public function getTenants(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/tenants");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Tenants Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get aggregated tenant health scores.
     */
    public function getTenantHealth(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/tenants/health");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Tenant Health Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Enable a tenant (set status to active).
     */
    public function enableTenant(int $id): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/tenants/{$id}/enable");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Tenant Enable Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Disable a tenant (set status to inactive).
     */
    public function disableTenant(int $id): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/tenants/{$id}/disable");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Tenant Disable Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Trigger an immediate health check for a specific tenant.
     */
    public function checkTenant(int $id): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(20)->post("{$this->baseUrl}/tenants/{$id}/check");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Tenant Check Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    // ── Audit Log API ─────────────────────────────────────────────────────

    /**
     * Get paginated audit log entries with optional filters.
     */
    public function getAuditLogs(array $filters = [], int $page = 1, int $perPage = 50): array
    {
        try {
            $params = array_merge($filters, [
                'page' => $page,
                'per_page' => $perPage,
            ]);

            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->get("{$this->baseUrl}/audit-logs", $params);

            return $response->json() ?? ['items' => [], 'total' => 0, 'page' => 1, 'per_page' => $perPage, 'pages' => 0];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Audit Logs Error: '.$e->getMessage());

            return ['items' => [], 'total' => 0, 'page' => 1, 'per_page' => $perPage, 'pages' => 0];
        }
    }

    // ── API Documentation ─────────────────────────────────────────────────

    /**
     * Fetch the OpenAPI specification from the backend.
     */
    public function getOpenApiSpec(): array
    {
        try {
            // OpenAPI spec is served at the root path, not under /api
            $rootUrl = str_replace('/api', '', $this->baseUrl);
            $response = Http::timeout(15)->get("{$rootUrl}/openapi.json");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine OpenAPI Spec Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get a single audit log entry by ID.
     */
    public function getAuditLogEntry(int $id): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/audit-logs/{$id}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Audit Log Entry Error: '.$e->getMessage());

            return [];
        }
    }

    // ── Alert Rule CRUD API ───────────────────────────────────────────────

    /**
     * List all alert rules.
     */
    public function getAlertRules(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->get("{$this->baseUrl}/alert-rules");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Alert Rules Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Create a new alert rule.
     */
    public function createAlertRule(array $data): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->post("{$this->baseUrl}/alert-rules", $data);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Create Alert Rule Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Update an existing alert rule.
     */
    public function updateAlertRule(int $id, array $data): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->put("{$this->baseUrl}/alert-rules/{$id}", $data);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Update Alert Rule Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Delete an alert rule.
     */
    public function deleteAlertRule(int $id): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->delete("{$this->baseUrl}/alert-rules/{$id}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Delete Alert Rule Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    // ── SanaaBrain Memory API ─────────────────────────────────────────────

    /**
     * Add a new memory entry to the persistent store.
     */
    public function addMemory(
        string $content,
        string $category = 'general',
        ?string $project = null,
        array $metadata = [],
        float $confidence = 1.0
    ): array {
        try {
            $payload = [
                'content' => $content,
                'category' => $category,
                'confidence' => $confidence,
                'metadata' => $metadata,
            ];
            if ($project !== null && $project !== '') {
                $payload['project'] = $project;
            }

            $response = Http::withToken($this->apiKey)
                ->timeout(20)
                ->post("{$this->baseUrl}/memory/add", $payload);

            return $response->json() ?? ['error' => 'Empty response'];
        } catch (\Exception $e) {
            Log::error('SanaaBrain addMemory Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Semantic search across stored memories.
     * Returns the array of result records directly (not the wrapper object).
     */
    public function searchMemory(
        string $query,
        int $limit = 10,
        ?string $category = null,
        ?string $project = null
    ): array {
        try {
            $params = ['query' => $query, 'limit' => $limit];
            if ($category !== null && $category !== '') {
                $params['category'] = $category;
            }
            if ($project !== null && $project !== '') {
                $params['project'] = $project;
            }

            $response = Http::withToken($this->apiKey)
                ->timeout(20)
                ->get("{$this->baseUrl}/memory/search", $params);

            $data = $response->json() ?? [];

            // API wraps results in {"query":…,"results":[…]}; return just the list.
            return $data['results'] ?? (array_is_list($data) ? $data : []);
        } catch (\Exception $e) {
            Log::error('SanaaBrain searchMemory Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get a formatted markdown briefing for a project's top memories.
     */
    public function getMemoryBriefing(string $project): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->get("{$this->baseUrl}/memory/briefing/{$project}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain getMemoryBriefing Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * List all memories with optional filters and pagination.
     */
    public function getAllMemories(
        ?string $project = null,
        ?string $category = null,
        int $limit = 50,
        int $offset = 0
    ): array {
        try {
            $params = ['limit' => $limit, 'offset' => $offset];
            if ($project !== null && $project !== '') {
                $params['project'] = $project;
            }
            if ($category !== null && $category !== '') {
                $params['category'] = $category;
            }

            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->get("{$this->baseUrl}/memory/all", $params);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain getAllMemories Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Save a session log as a memory entry.
     */
    public function saveMemorySession(
        string $content,
        string $sessionId = 'admin:sanaa-brain',
        ?string $project = null
    ): array {
        try {
            $payload = ['content' => $content, 'session_id' => $sessionId];
            if ($project !== null && $project !== '') {
                $payload['project'] = $project;
            }

            $response = Http::withToken($this->apiKey)
                ->timeout(20)
                ->post("{$this->baseUrl}/memory/session/save", $payload);

            return $response->json() ?? ['error' => 'Empty response'];
        } catch (\Exception $e) {
            Log::error('SanaaBrain saveMemorySession Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Delete a single memory entry by ID.
     */
    public function deleteMemory(int $memoryId): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->delete("{$this->baseUrl}/memory/{$memoryId}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain deleteMemory Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    // ── SanaaBrain Intelligence API ───────────────────────────────────────

    /**
     * Get auto-learned brain insights, optionally filtered by category and project.
     */
    public function getBrainInsights(string $category = '', string $project = ''): array
    {
        try {
            $params = ['limit' => 50];
            if ($category !== '') {
                $params['category'] = $category;
            }
            if ($project !== '') {
                $params['project'] = $project;
            }

            $response = Http::withToken($this->apiKey)
                ->timeout(20)
                ->get("{$this->baseUrl}/brain/insights", $params);

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain getBrainInsights Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get the last 4 weekly habit intelligence entries.
     */
    public function getBrainHabits(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->get("{$this->baseUrl}/brain/habits");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain getBrainHabits Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get a smart briefing for a project (enhanced multi-section briefing).
     */
    public function getSmartBriefing(string $project): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(30)
                ->get("{$this->baseUrl}/brain/smart_briefing/{$project}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain getSmartBriefing Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Trigger the SanaaBrain learner synchronously (learn_now).
     */
    public function triggerLearnNow(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(130)
                ->post("{$this->baseUrl}/brain/learn_now");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain triggerLearnNow Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Get LLM resource usage summaries from the last 7 days.
     */
    public function getResourceUsage(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->get("{$this->baseUrl}/brain/resource_usage");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain getResourceUsage Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Get client intelligence entries (tenant health, at-risk clients).
     */
    public function getClientIntelligence(): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->get("{$this->baseUrl}/brain/client_intelligence");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain getClientIntelligence Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * Delete all memories belonging to a project.
     */
    public function clearProjectMemory(string $project): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(15)
                ->delete("{$this->baseUrl}/memory/clear/{$project}");

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('SanaaBrain clearProjectMemory Error: '.$e->getMessage());

            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Aggregate Device Army statistics from the Python backend.
     */
    public function getDeviceArmyStats(): array
    {
        try {
            $response = $this->client(10)->get("{$this->baseUrl}/device-army/stats");

            if ($response->failed()) {
                $this->recordError('Sanaa Engine Device Army Stats Failed', $this->buildHttpFailureMessage('device-army/stats', $response), $response);

                return [];
            }

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Device Army Stats Error: '.$e->getMessage());

            return [];
        }
    }

    /**
     * List connected Device Army workers for dock and dashboard surfaces.
     */
    public function getDeviceArmyDevices(int $limit = 8): array
    {
        try {
            $response = $this->client(10)->get("{$this->baseUrl}/device-army/devices", [
                'limit' => $limit,
            ]);

            if ($response->failed()) {
                $this->recordError('Sanaa Engine Device Army Devices Failed', $this->buildHttpFailureMessage('device-army/devices', $response), $response);

                return ['devices' => []];
            }

            $payload = $response->json() ?? [];
            $devices = collect($payload['devices'] ?? [])->take($limit)->values()->all();

            return [
                'total' => (int) ($payload['total'] ?? count($devices)),
                'devices' => $devices,
            ];
        } catch (\Exception $e) {
            Log::error('Sanaa Engine Device Army Devices Error: '.$e->getMessage());

            return ['devices' => []];
        }
    }

    /**
     * Soko marketplace pulse for dock badge and live shell data.
     */
    public function getSokoPulse(): array
    {
        try {
            $response = $this->client(8)->get("{$this->baseUrl}/soko/pulse", ['limit' => 12]);

            if ($response->failed()) {
                return ['badge' => 0, 'success' => false];
            }

            $payload = $response->json() ?? [];

            return [
                'success' => (bool) ($payload['success'] ?? false),
                'badge' => (int) ($payload['badge'] ?? 0),
                'summary' => $payload['summary'] ?? [],
                'needs_you_count' => count($payload['needs_you'] ?? []),
            ];
        } catch (\Exception $e) {
            Log::debug('Soko pulse unavailable: '.$e->getMessage());

            return ['badge' => 0, 'success' => false];
        }
    }
}
