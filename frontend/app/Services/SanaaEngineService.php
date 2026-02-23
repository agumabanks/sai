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
                ->timeout(30)  // 30s timeout for LLM responses
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
}
