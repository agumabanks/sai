<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class SanaaEngineService
{
    protected string $baseUrl;
    protected string $apiKey;

    public function __construct()
    {
        // Internal proxy to the Python backend
        $this->baseUrl = config('services.sanaa_engine.url', 'http://127.0.0.1:8101/api');
        $this->apiKey = config('services.sanaa_engine.key', '');
    }

    /**
     * Get the current system status.
     */
    public function getStatus(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->get("{$this->baseUrl}/status");
            return $response->json() ?? ['status' => 'offline'];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Status Error: " . $e->getMessage());
            return ['status' => 'offline', 'error' => $e->getMessage()];
        }
    }

    /**
     * Execute a command.
     */
    public function executeCommand(string $command): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(120)
                ->post("{$this->baseUrl}/command", [
                    'command' => $command,
                ]);
                
            if ($response->failed()) {
                Log::error("Sanaa Engine Command Failed", [
                    'status' => $response->status(),
                    'body' => $response->body()
                ]);
                return [
                    'error' => 'Backend returned error: ' . $response->status(),
                    'status' => 'failed'
                ];
            }
            
            return $response->json() ?? ['error' => 'Invalid response format'];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Command Error: " . $e->getMessage());
            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    public function executeCommandAsync(string $command): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(10)
                ->post("{$this->baseUrl}/command", [
                    'command' => $command,
                    'async' => true,
                ]);
            return $response->json() ?? ['error' => 'Invalid response'];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Async Command Error: " . $e->getMessage());
            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    public function getCommandStatus(string $cmdId): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout(5)
                ->get("{$this->baseUrl}/command/{$cmdId}");
            return $response->json() ?? ['status' => 'unknown'];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Command Status Error: " . $e->getMessage());
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
                Log::info("Brain provider switched", ['provider' => $provider]);
                return true;
            }

            Log::error("Failed to switch brain provider", [
                'provider' => $provider,
                'status' => $response->status(),
                'body' => $response->body()
            ]);
            return false;
        } catch (\Exception $e) {
            Log::error("Brain provider switch error", [
                'provider' => $provider,
                'error' => $e->getMessage()
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
                Log::error("Failed to fetch brain config", [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);
                return [];
            }

            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Brain config fetch error", ['error' => $e->getMessage()]);
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

            Log::error("Failed to update brain config", [
                'status' => $response->status(),
                'body' => $response->body(),
                'payload_keys' => array_keys($payload),
            ]);
            return false;
        } catch (\Exception $e) {
            Log::error("Brain config update error", ['error' => $e->getMessage()]);
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
            Log::error("Sanaa Engine Activities Error: " . $e->getMessage());
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
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Briefings Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Briefing Detail Error: " . $e->getMessage());
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
            return $response->json() ?? ['status' => 'none'];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Signal Error: " . $e->getMessage());
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
            return (is_array($data) && (!empty($data) ? array_is_list($data) : true)) ? $data : [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Signals Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Wisdom Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Alerts Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Preference Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Get Preferences Error: " . $e->getMessage());
            return [];
        }
    }

    public function getToolPolicy(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/system/tool-policy");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Tool Policy Error: " . $e->getMessage());
            return [];
        }
    }

    public function updateToolPolicy(array $payload): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->post("{$this->baseUrl}/system/tool-policy", $payload);
            return $response->json() ?? ['status' => 'failed'];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Tool Policy Update Error: " . $e->getMessage());
            return ['status' => 'failed', 'error' => $e->getMessage()];
        }
    }

    public function getSkills(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Skills Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Skill Toggle Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Skill Exposure Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    /**
     * Run a specific skill with the given arguments.
     */
    public function runSkill(string $skillName, array $args = [], string $sessionId = '', int $timeout = 60): array
    {
        try {
            $response = Http::withToken($this->apiKey)
                ->timeout($timeout)
                ->post("{$this->baseUrl}/skills/{$skillName}/run", [
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
                return ['success' => false, 'error' => 'HTTP ' . $response->status() . ': ' . $response->body()];
            }
            return $json ?: ['success' => false, 'error' => 'Empty response'];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Skill Run Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Workflows Error: " . $e->getMessage());
            return [];
        }
    }

    public function getWorkflowRuns(int $limit = 50): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/workflows/runs", ['limit' => $limit]);
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Workflow Runs Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Workflow Start Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    public function getWorkflowRun(int $runId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/workflows/runs/{$runId}");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Workflow Run Error: " . $e->getMessage());
            return [];
        }
    }

    public function getWorkflowApproval(int $runId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/workflows/runs/{$runId}/approval");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Workflow Approval Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Workflow Resume Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    public function cancelWorkflowRun(int $runId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/workflows/runs/{$runId}/cancel");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Workflow Cancel Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Workflow Save Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    public function getSessionPolicy(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/system/session-policy");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Session Policy Error: " . $e->getMessage());
            return [];
        }
    }

    public function updateSessionPolicy(array $payload): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->post("{$this->baseUrl}/system/session-policy", $payload);
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Session Policy Update Error: " . $e->getMessage());
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
            Log::error("Sanaa ML Scores Error: " . $e->getMessage());
            return [];
        }
    }

    public function getSkillMLScore(string $skillName): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills/{$skillName}/ml/score");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa ML Skill Score Error: " . $e->getMessage());
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
            Log::error("Sanaa ML Metrics Error: " . $e->getMessage());
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
            Log::error("Sanaa ML Feedback Error: " . $e->getMessage());
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
            Log::error("Sanaa ML Learning Log Error: " . $e->getMessage());
            return [];
        }
    }

    public function getSkillParameterInsights(string $skillName): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(15)->get("{$this->baseUrl}/skills/{$skillName}/ml/parameters");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa ML Parameters Error: " . $e->getMessage());
            return [];
        }
    }

    public function triggerMLAnalysis(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(60)->post("{$this->baseUrl}/skills/ml/analyze");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa ML Analysis Error: " . $e->getMessage());
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
            Log::error("Sanaa ML Global Learning Log Error: " . $e->getMessage());
            return [];
        }
    }

    public function getSessions(int $limit = 100): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/sessions", ['limit' => $limit]);
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Sessions Error: " . $e->getMessage());
            return [];
        }
    }

    public function getSessionDetail(string $sessionId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/sessions/{$sessionId}");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Session Detail Error: " . $e->getMessage());
            return [];
        }
    }

    public function resetSession(string $sessionId): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->post("{$this->baseUrl}/sessions/{$sessionId}/reset");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Session Reset Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Session Send Policy Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }

    public function getDoctorReport(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(20)->get("{$this->baseUrl}/system/doctor");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Doctor Error: " . $e->getMessage());
            return [];
        }
    }

    public function getWatchdogAdvisor(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/intelligence/advisor/watchdog");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Watchdog Advisor Error: " . $e->getMessage());
            return [];
        }
    }

    public function getLatestBriefingQa(): array
    {
        try {
            $response = Http::withToken($this->apiKey)->timeout(10)->get("{$this->baseUrl}/intelligence/briefings/qa/latest");
            return $response->json() ?? [];
        } catch (\Exception $e) {
            Log::error("Sanaa Engine Briefing QA Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Marketing Metrics Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Social Analytics Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Scheduled Content Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Memories Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Learning Logs Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Tenants Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Tenant Health Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Tenant Enable Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Tenant Disable Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Tenant Check Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Audit Logs Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine OpenAPI Spec Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Audit Log Entry Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Alert Rules Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Create Alert Rule Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Update Alert Rule Error: " . $e->getMessage());
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
            Log::error("Sanaa Engine Delete Alert Rule Error: " . $e->getMessage());
            return ['error' => $e->getMessage()];
        }
    }
}
