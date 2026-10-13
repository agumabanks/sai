<?php

namespace App\Filament\Pages;

use App\Services\SanaaEngineService;
use Filament\Notifications\Notification;
use Filament\Pages\Page;

class WorkflowBuilder extends Page
{
    protected static ?string $navigationIcon = 'heroicon-o-arrow-path';

    protected static ?string $navigationGroup = 'Skills Lab';

    protected static ?int $navigationSort = 3;

    protected static string $view = 'filament.pages.workflow-builder';

    protected static ?string $title = 'Workflow Builder';

    protected static ?string $navigationLabel = 'Workflow Builder';

    // ── Workflow metadata ─────────────────────────────────────────────────

    public string $workflowName = '';

    public string $workflowDescription = '';

    public string $workflowVersion = '1.0.0';

    // ── Builder state ─────────────────────────────────────────────────────

    /** @var array<int, array{type: string, id: string, config: array, description: string}> */
    public array $workflowSteps = [];

    /** Generated YAML output */
    public string $generatedYaml = '';

    /** Existing workflows for loading */
    public array $existingWorkflows = [];

    /** Available skills for the palette */
    public array $availableSkills = [];

    /** Step currently being configured (index or null) */
    public ?int $editingStepIndex = null;

    /** Whether the YAML preview panel is open */
    public bool $showYamlPreview = false;

    // ── Step type definitions (palette) ───────────────────────────────────

    /**
     * Get available step types for the palette.
     */
    public function getStepTypes(): array
    {
        return [
            'skill' => [
                'label' => 'Skill Execution',
                'icon' => 'heroicon-o-bolt',
                'description' => 'Execute a registered skill with arguments',
                'color' => 'indigo',
            ],
            'condition' => [
                'label' => 'Condition Check',
                'icon' => 'heroicon-o-funnel',
                'description' => 'Evaluate a condition before proceeding',
                'color' => 'amber',
            ],
            'delay' => [
                'label' => 'Delay',
                'icon' => 'heroicon-o-clock',
                'description' => 'Wait for a specified duration',
                'color' => 'cyan',
            ],
            'notify' => [
                'label' => 'Notification',
                'icon' => 'heroicon-o-bell',
                'description' => 'Send a notification via a channel',
                'color' => 'emerald',
            ],
            'llm' => [
                'label' => 'LLM Analysis',
                'icon' => 'heroicon-o-cpu-chip',
                'description' => 'Run an LLM prompt to analyse or summarise data',
                'color' => 'purple',
            ],
            'shell' => [
                'label' => 'Shell Command',
                'icon' => 'heroicon-o-command-line',
                'description' => 'Execute a shell command (requires approval)',
                'color' => 'rose',
            ],
        ];
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────

    public function mount(): void
    {
        $this->refreshData();
    }

    public function refreshData(): void
    {
        $engine = app(SanaaEngineService::class);
        $data = $engine->getWorkflows();
        $this->existingWorkflows = $data['workflows'] ?? [];

        $skillsData = $engine->getSkills();
        $this->availableSkills = array_map(
            fn ($s) => $s['name'] ?? '',
            $skillsData['skills'] ?? []
        );
    }

    // ── Step management ───────────────────────────────────────────────────

    /**
     * Add a new step of the given type to the workflow.
     */
    public function addStep(string $type): void
    {
        $stepIndex = count($this->workflowSteps);
        $stepId = $this->generateStepId($type, $stepIndex);

        $config = $this->getDefaultConfig($type);

        $this->workflowSteps[] = [
            'type' => $type,
            'id' => $stepId,
            'description' => '',
            'config' => $config,
        ];
    }

    /**
     * Remove a step by its index.
     */
    public function removeStep(int $index): void
    {
        if (isset($this->workflowSteps[$index])) {
            array_splice($this->workflowSteps, $index, 1);
            $this->workflowSteps = array_values($this->workflowSteps);

            if ($this->editingStepIndex === $index) {
                $this->editingStepIndex = null;
            } elseif ($this->editingStepIndex !== null && $this->editingStepIndex > $index) {
                $this->editingStepIndex--;
            }
        }
    }

    /**
     * Move a step up in the sequence.
     */
    public function moveStepUp(int $index): void
    {
        if ($index > 0 && $index < count($this->workflowSteps)) {
            $temp = $this->workflowSteps[$index];
            $this->workflowSteps[$index] = $this->workflowSteps[$index - 1];
            $this->workflowSteps[$index - 1] = $temp;
            $this->workflowSteps = array_values($this->workflowSteps);
        }
    }

    /**
     * Move a step down in the sequence.
     */
    public function moveStepDown(int $index): void
    {
        if ($index < count($this->workflowSteps) - 1) {
            $temp = $this->workflowSteps[$index];
            $this->workflowSteps[$index] = $this->workflowSteps[$index + 1];
            $this->workflowSteps[$index + 1] = $temp;
            $this->workflowSteps = array_values($this->workflowSteps);
        }
    }

    /**
     * Update a configuration field for a specific step.
     */
    public function updateStepConfig(int $index, string $key, mixed $value): void
    {
        if (isset($this->workflowSteps[$index])) {
            $this->workflowSteps[$index]['config'][$key] = $value;
        }
    }

    /**
     * Select a step for editing in the config panel.
     */
    public function editStep(int $index): void
    {
        $this->editingStepIndex = $index;
    }

    /**
     * Close the step config panel.
     */
    public function closeStepEditor(): void
    {
        $this->editingStepIndex = null;
    }

    // ── YAML generation ───────────────────────────────────────────────────

    /**
     * Generate YAML from the current builder state.
     */
    public function generateYaml(): void
    {
        $workflow = $this->buildWorkflowArray();
        $this->generatedYaml = $this->arrayToYaml($workflow);
        $this->showYamlPreview = true;
    }

    /**
     * Build the workflow array that mirrors the backend YAML schema.
     */
    public function buildWorkflowArray(): array
    {
        $workflow = [
            'name' => $this->workflowName ?: 'untitled_workflow',
            'version' => $this->workflowVersion ?: '1.0.0',
            'description' => $this->workflowDescription ?: '',
        ];

        $steps = [];
        $previousStepId = null;

        foreach ($this->workflowSteps as $step) {
            $stepDef = [
                'id' => $step['id'] ?? 'step_'.count($steps),
                'action' => $this->resolveAction($step['type']),
                'description' => $step['description'] ?? '',
                'params' => $this->buildStepParams($step),
            ];

            // Add depends_on for sequential linking
            if ($previousStepId !== null) {
                $stepDef['depends_on'] = [$previousStepId];
            }

            // Add approval flag for shell commands
            if (($step['type'] ?? '') === 'shell') {
                $stepDef['approval'] = true;
            }

            // Add condition for condition-type steps
            $condition = $step['config']['condition'] ?? '';
            if ($condition !== '' && $step['type'] === 'condition') {
                $stepDef['condition'] = $condition;
            }

            // Add on_failure policy
            $onFailure = $step['config']['on_failure'] ?? '';
            if ($onFailure !== '' && $onFailure !== 'abort') {
                $stepDef['on_failure'] = $onFailure;
            }

            // Add timeout
            $timeout = (int) ($step['config']['timeout'] ?? 0);
            if ($timeout > 0 && $timeout !== 60) {
                $stepDef['timeout'] = $timeout;
            }

            $steps[] = $stepDef;
            $previousStepId = $stepDef['id'];
        }

        $workflow['steps'] = $steps;

        return $workflow;
    }

    /**
     * Save the workflow to the backend.
     */
    public function saveWorkflow(): void
    {
        if (trim($this->workflowName) === '') {
            Notification::make()->title('Workflow name is required')->warning()->send();

            return;
        }

        if (empty($this->workflowSteps)) {
            Notification::make()->title('Add at least one step')->warning()->send();

            return;
        }

        $this->generateYaml();

        $engine = app(SanaaEngineService::class);
        $result = $engine->saveWorkflow($this->generatedYaml);

        if (! empty($result['error'])) {
            Notification::make()
                ->title('Failed to save workflow')
                ->body((string) $result['error'])
                ->danger()
                ->send();

            return;
        }

        Notification::make()
            ->title("Workflow saved: {$this->workflowName}")
            ->success()
            ->send();

        $this->refreshData();
    }

    /**
     * Load an existing workflow into the builder.
     */
    public function loadWorkflow(string $name): void
    {
        $workflow = null;
        foreach ($this->existingWorkflows as $wf) {
            if (($wf['name'] ?? '') === $name) {
                $workflow = $wf;
                break;
            }
        }

        if (! $workflow) {
            Notification::make()->title("Workflow not found: {$name}")->danger()->send();

            return;
        }

        $this->workflowName = $workflow['name'] ?? '';
        $this->workflowDescription = $workflow['description'] ?? '';
        $this->workflowVersion = $workflow['version'] ?? '1.0.0';

        $this->workflowSteps = [];
        foreach ($workflow['steps'] ?? [] as $step) {
            $type = $this->resolveType($step['action'] ?? 'skill');
            $this->workflowSteps[] = [
                'type' => $type,
                'id' => $step['id'] ?? 'step_'.count($this->workflowSteps),
                'description' => $step['description'] ?? '',
                'config' => $this->extractConfig($step, $type),
            ];
        }

        Notification::make()
            ->title("Loaded workflow: {$name}")
            ->success()
            ->send();
    }

    /**
     * Clear the builder state.
     */
    public function clearBuilder(): void
    {
        $this->workflowName = '';
        $this->workflowDescription = '';
        $this->workflowVersion = '1.0.0';
        $this->workflowSteps = [];
        $this->generatedYaml = '';
        $this->editingStepIndex = null;
        $this->showYamlPreview = false;
    }

    /**
     * Toggle the YAML preview panel.
     */
    public function toggleYamlPreview(): void
    {
        if (! $this->showYamlPreview) {
            $this->generateYaml();
        } else {
            $this->showYamlPreview = false;
        }
    }

    // ── Private helpers ───────────────────────────────────────────────────

    /**
     * Generate a step ID from type and index.
     */
    protected function generateStepId(string $type, int $index): string
    {
        $prefix = match ($type) {
            'skill' => 'run_skill',
            'condition' => 'check',
            'delay' => 'wait',
            'notify' => 'notify',
            'llm' => 'analyse',
            'shell' => 'exec',
            default => 'step',
        };

        return $prefix.'_'.($index + 1);
    }

    /**
     * Get default configuration for a step type.
     */
    protected function getDefaultConfig(string $type): array
    {
        return match ($type) {
            'skill' => [
                'skill_name' => '',
                'args' => '{}',
                'description' => '',
                'on_failure' => 'abort',
                'timeout' => 60,
            ],
            'condition' => [
                'condition' => '',
                'description' => '',
                'on_failure' => 'skip',
            ],
            'delay' => [
                'seconds' => 10,
                'description' => '',
            ],
            'notify' => [
                'channel' => 'web',
                'message' => '',
                'description' => '',
            ],
            'llm' => [
                'prompt' => '',
                'complexity' => 'medium',
                'description' => '',
                'on_failure' => 'abort',
            ],
            'shell' => [
                'command' => '',
                'description' => '',
                'on_failure' => 'skip',
                'timeout' => 60,
            ],
            default => [
                'description' => '',
            ],
        };
    }

    /**
     * Map builder type to backend action name.
     */
    protected function resolveAction(string $type): string
    {
        return match ($type) {
            'skill' => 'skill',
            'condition' => 'skill',
            'delay' => 'delay',
            'notify' => 'notify',
            'llm' => 'llm',
            'shell' => 'shell',
            default => 'skill',
        };
    }

    /**
     * Map backend action name to builder type.
     */
    protected function resolveType(string $action): string
    {
        return match ($action) {
            'skill' => 'skill',
            'delay' => 'delay',
            'notify' => 'notify',
            'llm' => 'llm',
            'shell' => 'shell',
            default => 'skill',
        };
    }

    /**
     * Build step params from builder config for YAML output.
     */
    protected function buildStepParams(array $step): array
    {
        $type = $step['type'] ?? 'skill';
        $config = $step['config'] ?? [];

        return match ($type) {
            'skill' => [
                'skill' => $config['skill_name'] ?? '',
                'args' => $this->parseJsonConfig($config['args'] ?? '{}'),
            ],
            'condition' => [
                'skill' => $config['skill_name'] ?? 'server_health',
                'args' => $this->parseJsonConfig($config['args'] ?? '{}'),
            ],
            'delay' => [
                'seconds' => (int) ($config['seconds'] ?? 10),
            ],
            'notify' => [
                'channel' => $config['channel'] ?? 'web',
                'message' => $config['message'] ?? '',
            ],
            'llm' => [
                'prompt' => $config['prompt'] ?? '',
                'complexity' => $config['complexity'] ?? 'medium',
            ],
            'shell' => [
                'command' => $config['command'] ?? '',
            ],
            default => [],
        };
    }

    /**
     * Extract builder config from a backend step definition.
     */
    protected function extractConfig(array $step, string $type): array
    {
        $params = $step['params'] ?? [];

        return match ($type) {
            'skill' => [
                'skill_name' => $params['skill'] ?? '',
                'args' => json_encode($params['args'] ?? new \stdClass, JSON_PRETTY_PRINT),
                'description' => $step['description'] ?? '',
                'on_failure' => $step['on_failure'] ?? 'abort',
                'timeout' => $step['timeout'] ?? 60,
            ],
            'delay' => [
                'seconds' => $params['seconds'] ?? 10,
                'description' => $step['description'] ?? '',
            ],
            'notify' => [
                'channel' => $params['channel'] ?? 'web',
                'message' => $params['message'] ?? '',
                'description' => $step['description'] ?? '',
            ],
            'llm' => [
                'prompt' => $params['prompt'] ?? '',
                'complexity' => $params['complexity'] ?? 'medium',
                'description' => $step['description'] ?? '',
                'on_failure' => $step['on_failure'] ?? 'abort',
            ],
            'shell' => [
                'command' => $params['command'] ?? '',
                'description' => $step['description'] ?? '',
                'on_failure' => $step['on_failure'] ?? 'skip',
                'timeout' => $step['timeout'] ?? 60,
            ],
            default => [
                'description' => $step['description'] ?? '',
            ],
        };
    }

    /**
     * Parse a JSON string config value, returning an empty object on failure.
     */
    protected function parseJsonConfig(string $json): array|object
    {
        $decoded = json_decode($json, true);
        if (json_last_error() !== JSON_ERROR_NONE || ! is_array($decoded)) {
            return new \stdClass;
        }

        return $decoded ?: new \stdClass;
    }

    /**
     * Convert an array to YAML string (simple implementation).
     */
    protected function arrayToYaml(array $data, int $indent = 0): string
    {
        $yaml = '';
        $prefix = str_repeat('  ', $indent);

        foreach ($data as $key => $value) {
            if (is_int($key)) {
                // List item
                if (is_array($value)) {
                    $yaml .= $prefix.'- ';
                    $first = true;
                    foreach ($value as $subKey => $subValue) {
                        if ($first) {
                            $yaml .= $this->formatYamlKeyValue($subKey, $subValue, $indent + 1, true);
                            $first = false;
                        } else {
                            $yaml .= $this->formatYamlKeyValue($subKey, $subValue, $indent + 1);
                        }
                    }
                } else {
                    $yaml .= $prefix.'- '.$this->formatYamlValue($value)."\n";
                }
            } else {
                $yaml .= $this->formatYamlKeyValue($key, $value, $indent);
            }
        }

        return $yaml;
    }

    /**
     * Format a key-value pair as YAML.
     */
    protected function formatYamlKeyValue(string $key, mixed $value, int $indent, bool $inline = false): string
    {
        $prefix = $inline ? '' : str_repeat('  ', $indent);

        if (is_array($value)) {
            if (empty($value)) {
                return $prefix.$key.": {}\n";
            }

            // Check if it's a list
            if (array_is_list($value)) {
                $result = $prefix.$key.":\n";
                foreach ($value as $item) {
                    if (is_array($item)) {
                        $result .= $this->arrayToYaml([$item], $indent + 1);
                    } else {
                        $result .= str_repeat('  ', $indent + 1).'- '.$this->formatYamlValue($item)."\n";
                    }
                }

                return $result;
            }

            // Associative array
            $result = $prefix.$key.":\n";
            $result .= $this->arrayToYaml($value, $indent + 1);

            return $result;
        }

        return $prefix.$key.': '.$this->formatYamlValue($value)."\n";
    }

    /**
     * Format a scalar value for YAML.
     */
    protected function formatYamlValue(mixed $value): string
    {
        if ($value === null) {
            return 'null';
        }
        if (is_bool($value)) {
            return $value ? 'true' : 'false';
        }
        if (is_int($value) || is_float($value)) {
            return (string) $value;
        }
        if (is_string($value)) {
            // Quote strings with special characters or multi-line
            if ($value === '' || str_contains($value, "\n") || str_contains($value, ':') || str_contains($value, '#') || str_contains($value, '{') || str_contains($value, '}') || str_contains($value, '[') || str_contains($value, ']')) {
                return '"'.addcslashes($value, '"\\').'"';
            }
            // Quote strings that look like booleans or numbers
            if (in_array(strtolower($value), ['true', 'false', 'null', 'yes', 'no'], true)) {
                return '"'.$value.'"';
            }

            return $value;
        }
        if ($value instanceof \stdClass) {
            return '{}';
        }

        return (string) $value;
    }
}
