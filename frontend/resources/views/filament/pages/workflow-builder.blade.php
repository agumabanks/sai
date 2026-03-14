<x-filament-panels::page>
    <div class="space-y-6">

        {{-- ── Header: Workflow Metadata ────────────────────────────────── --}}
        <div class="glass-dark rounded-xl p-6">
            <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div class="flex-1 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-gray-400 mb-1">Workflow Name</label>
                        <input type="text"
                               wire:model.live="workflowName"
                               placeholder="e.g. daily_triage"
                               class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-400 mb-1">Description</label>
                        <input type="text"
                               wire:model.live="workflowDescription"
                               placeholder="What this workflow does"
                               class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-400 mb-1">Version</label>
                        <input type="text"
                               wire:model.live="workflowVersion"
                               placeholder="1.0.0"
                               class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <x-filament::button size="sm" color="success" wire:click="saveWorkflow" icon="heroicon-o-cloud-arrow-up">
                        Save
                    </x-filament::button>
                    <x-filament::button size="sm" color="gray" wire:click="toggleYamlPreview" icon="heroicon-o-code-bracket">
                        YAML
                    </x-filament::button>
                    <x-filament::button size="sm" color="danger" wire:click="clearBuilder" icon="heroicon-o-trash">
                        Clear
                    </x-filament::button>
                    <x-filament::button size="sm" color="gray" wire:click="refreshData" icon="heroicon-o-arrow-path">
                        Refresh
                    </x-filament::button>
                </div>
            </div>
        </div>

        <div class="grid gap-6 lg:grid-cols-4">

            {{-- ── Left Panel: Step Palette & Existing Workflows ────────── --}}
            <div class="lg:col-span-1 space-y-6">

                {{-- Step Palette --}}
                <div class="glass-dark rounded-xl p-4">
                    <h3 class="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                        <x-heroicon-o-squares-plus class="w-4 h-4 text-sanaa-indigo" />
                        Step Palette
                    </h3>
                    <p class="text-xs text-gray-500 mb-3">Click to add a step to your workflow</p>
                    <div class="space-y-2">
                        @foreach ($this->getStepTypes() as $type => $meta)
                            <button wire:click="addStep('{{ $type }}')"
                                    class="w-full flex items-center gap-3 rounded-lg border border-gray-700/50 bg-gray-800/50 p-3 text-left transition hover:border-sanaa-{{ $meta['color'] }}/50 hover:bg-gray-800 group">
                                <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sanaa-{{ $meta['color'] }}/10 text-sanaa-{{ $meta['color'] }}">
                                    <x-dynamic-component :component="$meta['icon']" class="w-4 h-4" />
                                </div>
                                <div class="min-w-0">
                                    <div class="text-sm font-medium text-gray-200 group-hover:text-white">{{ $meta['label'] }}</div>
                                    <div class="text-xs text-gray-500 truncate">{{ $meta['description'] }}</div>
                                </div>
                            </button>
                        @endforeach
                    </div>
                </div>

                {{-- Existing Workflows --}}
                <div class="glass-dark rounded-xl p-4">
                    <h3 class="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                        <x-heroicon-o-document-duplicate class="w-4 h-4 text-sanaa-emerald" />
                        Existing Workflows
                    </h3>
                    <div class="space-y-2 max-h-64 overflow-y-auto">
                        @forelse ($existingWorkflows as $wf)
                            <button wire:click="loadWorkflow('{{ $wf['name'] ?? '' }}')"
                                    class="w-full text-left rounded-lg border border-gray-700/50 bg-gray-800/50 p-3 transition hover:border-sanaa-emerald/50 hover:bg-gray-800">
                                <div class="text-sm font-medium text-gray-200">{{ $wf['name'] ?? '-' }}</div>
                                <div class="text-xs text-gray-500 truncate">{{ $wf['description'] ?? '' }}</div>
                                <div class="mt-1 text-xs text-gray-600">{{ $wf['step_count'] ?? 0 }} steps</div>
                            </button>
                        @empty
                            <p class="text-xs text-gray-500">No workflows found.</p>
                        @endforelse
                    </div>
                </div>
            </div>

            {{-- ── Center Panel: Workflow Canvas ───────────────────────── --}}
            <div class="lg:col-span-2">
                <div class="glass-dark rounded-xl p-4 min-h-[500px]">
                    <h3 class="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
                        <x-heroicon-o-rectangle-stack class="w-4 h-4 text-sanaa-cyan" />
                        Workflow Steps
                        <span class="ml-auto text-xs font-normal text-gray-500">{{ count($workflowSteps) }} step(s)</span>
                    </h3>

                    @if (empty($workflowSteps))
                        <div class="flex flex-col items-center justify-center py-20 text-gray-500">
                            <x-heroicon-o-arrow-path class="w-12 h-12 mb-3 opacity-30" />
                            <p class="text-sm">No steps yet</p>
                            <p class="text-xs mt-1">Use the palette to add steps to your workflow</p>
                        </div>
                    @else
                        <div class="space-y-3">
                            @foreach ($workflowSteps as $index => $step)
                                @php
                                    $stepTypes = $this->getStepTypes();
                                    $meta = $stepTypes[$step['type']] ?? ['label' => 'Unknown', 'icon' => 'heroicon-o-question-mark-circle', 'color' => 'gray'];
                                @endphp
                                <div class="relative rounded-lg border {{ $editingStepIndex === $index ? 'border-sanaa-indigo ring-1 ring-sanaa-indigo/50' : 'border-gray-700/50' }} bg-gray-800/50 p-4 transition hover:border-gray-600">
                                    {{-- Step header --}}
                                    <div class="flex items-center justify-between">
                                        <div class="flex items-center gap-3">
                                            <span class="flex h-6 w-6 items-center justify-center rounded-full bg-gray-700 text-xs font-bold text-gray-300">{{ $index + 1 }}</span>
                                            <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-sanaa-{{ $meta['color'] }}/10 text-sanaa-{{ $meta['color'] }}">
                                                <x-dynamic-component :component="$meta['icon']" class="w-3.5 h-3.5" />
                                            </div>
                                            <div>
                                                <div class="text-sm font-medium text-gray-200">{{ $meta['label'] }}</div>
                                                <div class="text-xs text-gray-500">{{ $step['id'] ?? '' }}</div>
                                            </div>
                                        </div>
                                        <div class="flex items-center gap-1">
                                            @if ($index > 0)
                                                <button wire:click="moveStepUp({{ $index }})" class="p-1 text-gray-500 hover:text-white" title="Move up">
                                                    <x-heroicon-o-chevron-up class="w-4 h-4" />
                                                </button>
                                            @endif
                                            @if ($index < count($workflowSteps) - 1)
                                                <button wire:click="moveStepDown({{ $index }})" class="p-1 text-gray-500 hover:text-white" title="Move down">
                                                    <x-heroicon-o-chevron-down class="w-4 h-4" />
                                                </button>
                                            @endif
                                            <button wire:click="editStep({{ $index }})" class="p-1 text-gray-500 hover:text-sanaa-indigo" title="Configure">
                                                <x-heroicon-o-cog-6-tooth class="w-4 h-4" />
                                            </button>
                                            <button wire:click="removeStep({{ $index }})" class="p-1 text-gray-500 hover:text-red-400" title="Remove">
                                                <x-heroicon-o-x-mark class="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>

                                    {{-- Step summary --}}
                                    @php
                                        $config = $step['config'] ?? [];
                                        $summary = match ($step['type']) {
                                            'skill' => 'Skill: ' . ($config['skill_name'] ?: '(not set)'),
                                            'condition' => 'Condition: ' . ($config['condition'] ?: '(not set)'),
                                            'delay' => 'Wait: ' . ($config['seconds'] ?? 10) . 's',
                                            'notify' => 'Channel: ' . ($config['channel'] ?? 'web'),
                                            'llm' => 'Prompt: ' . \Illuminate\Support\Str::limit($config['prompt'] ?? '', 60),
                                            'shell' => 'Cmd: ' . \Illuminate\Support\Str::limit($config['command'] ?? '', 60),
                                            default => '',
                                        };
                                    @endphp
                                    @if ($summary)
                                        <div class="mt-2 text-xs text-gray-400">{{ $summary }}</div>
                                    @endif
                                    @if (!empty($step['description']))
                                        <div class="mt-1 text-xs text-gray-500 italic">{{ $step['description'] }}</div>
                                    @endif

                                    {{-- Connection line to next step --}}
                                    @if ($index < count($workflowSteps) - 1)
                                        <div class="absolute -bottom-3 left-1/2 -translate-x-1/2 z-10">
                                            <x-heroicon-o-arrow-down class="w-4 h-4 text-gray-600" />
                                        </div>
                                    @endif
                                </div>
                            @endforeach
                        </div>
                    @endif
                </div>
            </div>

            {{-- ── Right Panel: Step Config Editor ──────────────────────── --}}
            <div class="lg:col-span-1">
                <div class="glass-dark rounded-xl p-4 sticky top-4">
                    @if ($editingStepIndex !== null && isset($workflowSteps[$editingStepIndex]))
                        @php
                            $editStep = $workflowSteps[$editingStepIndex];
                            $editType = $editStep['type'];
                            $editConfig = $editStep['config'] ?? [];
                        @endphp
                        <div class="flex items-center justify-between mb-4">
                            <h3 class="text-sm font-semibold text-gray-300">Configure Step #{{ $editingStepIndex + 1 }}</h3>
                            <button wire:click="closeStepEditor" class="p-1 text-gray-500 hover:text-white">
                                <x-heroicon-o-x-mark class="w-4 h-4" />
                            </button>
                        </div>

                        <div class="space-y-3">
                            {{-- Step ID --}}
                            <div>
                                <label class="block text-xs font-medium text-gray-400 mb-1">Step ID</label>
                                <input type="text"
                                       wire:model.live="workflowSteps.{{ $editingStepIndex }}.id"
                                       class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                            </div>

                            {{-- Description --}}
                            <div>
                                <label class="block text-xs font-medium text-gray-400 mb-1">Description</label>
                                <input type="text"
                                       wire:model.live="workflowSteps.{{ $editingStepIndex }}.description"
                                       placeholder="What this step does"
                                       class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                            </div>

                            {{-- Type-specific fields --}}
                            @if ($editType === 'skill')
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Skill Name</label>
                                    <select wire:change="updateStepConfig({{ $editingStepIndex }}, 'skill_name', $event.target.value)"
                                            class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">
                                        <option value="">Select a skill...</option>
                                        @foreach ($availableSkills as $skill)
                                            <option value="{{ $skill }}" {{ ($editConfig['skill_name'] ?? '') === $skill ? 'selected' : '' }}>{{ $skill }}</option>
                                        @endforeach
                                    </select>
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Arguments (JSON)</label>
                                    <textarea wire:change="updateStepConfig({{ $editingStepIndex }}, 'args', $event.target.value)"
                                              rows="3"
                                              class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-xs text-white font-mono focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">{{ $editConfig['args'] ?? '{}' }}</textarea>
                                </div>
                            @elseif ($editType === 'condition')
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Condition Expression</label>
                                    <input type="text"
                                           wire:change="updateStepConfig({{ $editingStepIndex }}, 'condition', $event.target.value)"
                                           value="{{ $editConfig['condition'] ?? '' }}"
                                           placeholder="e.g. steps.health_check.output contains 'error'"
                                           class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                                </div>
                            @elseif ($editType === 'delay')
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Delay (seconds)</label>
                                    <input type="number"
                                           wire:change="updateStepConfig({{ $editingStepIndex }}, 'seconds', $event.target.value)"
                                           value="{{ $editConfig['seconds'] ?? 10 }}"
                                           min="1"
                                           class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                                </div>
                            @elseif ($editType === 'notify')
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Channel</label>
                                    <select wire:change="updateStepConfig({{ $editingStepIndex }}, 'channel', $event.target.value)"
                                            class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">
                                        <option value="web" {{ ($editConfig['channel'] ?? '') === 'web' ? 'selected' : '' }}>Web</option>
                                        <option value="whatsapp" {{ ($editConfig['channel'] ?? '') === 'whatsapp' ? 'selected' : '' }}>WhatsApp</option>
                                        <option value="email" {{ ($editConfig['channel'] ?? '') === 'email' ? 'selected' : '' }}>Email</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Message</label>
                                    <textarea wire:change="updateStepConfig({{ $editingStepIndex }}, 'message', $event.target.value)"
                                              rows="3"
                                              placeholder="Use @{{ steps.step_id.output }} for references"
                                              class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-xs text-white font-mono placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">{{ $editConfig['message'] ?? '' }}</textarea>
                                </div>
                            @elseif ($editType === 'llm')
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Prompt</label>
                                    <textarea wire:change="updateStepConfig({{ $editingStepIndex }}, 'prompt', $event.target.value)"
                                              rows="5"
                                              placeholder="Enter LLM prompt..."
                                              class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-xs text-white font-mono placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">{{ $editConfig['prompt'] ?? '' }}</textarea>
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Complexity</label>
                                    <select wire:change="updateStepConfig({{ $editingStepIndex }}, 'complexity', $event.target.value)"
                                            class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">
                                        <option value="low" {{ ($editConfig['complexity'] ?? '') === 'low' ? 'selected' : '' }}>Low</option>
                                        <option value="medium" {{ ($editConfig['complexity'] ?? '') === 'medium' ? 'selected' : '' }}>Medium</option>
                                        <option value="high" {{ ($editConfig['complexity'] ?? '') === 'high' ? 'selected' : '' }}>High</option>
                                    </select>
                                </div>
                            @elseif ($editType === 'shell')
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Command</label>
                                    <textarea wire:change="updateStepConfig({{ $editingStepIndex }}, 'command', $event.target.value)"
                                              rows="3"
                                              placeholder="e.g. systemctl restart antigravity-web"
                                              class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-xs text-white font-mono placeholder-gray-500 focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">{{ $editConfig['command'] ?? '' }}</textarea>
                                </div>
                                <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-300">
                                    ⚠ Shell commands require approval before execution
                                </div>
                            @endif

                            {{-- On-failure policy (applicable to most types) --}}
                            @if (in_array($editType, ['skill', 'condition', 'llm', 'shell']))
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">On Failure</label>
                                    <select wire:change="updateStepConfig({{ $editingStepIndex }}, 'on_failure', $event.target.value)"
                                            class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo">
                                        <option value="abort" {{ ($editConfig['on_failure'] ?? 'abort') === 'abort' ? 'selected' : '' }}>Abort</option>
                                        <option value="skip" {{ ($editConfig['on_failure'] ?? '') === 'skip' ? 'selected' : '' }}>Skip</option>
                                        <option value="retry" {{ ($editConfig['on_failure'] ?? '') === 'retry' ? 'selected' : '' }}>Retry</option>
                                    </select>
                                </div>
                            @endif

                            {{-- Timeout (applicable to skill, shell) --}}
                            @if (in_array($editType, ['skill', 'shell']))
                                <div>
                                    <label class="block text-xs font-medium text-gray-400 mb-1">Timeout (seconds)</label>
                                    <input type="number"
                                           wire:change="updateStepConfig({{ $editingStepIndex }}, 'timeout', $event.target.value)"
                                           value="{{ $editConfig['timeout'] ?? 60 }}"
                                           min="1"
                                           class="w-full rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2 text-sm text-white focus:border-sanaa-indigo focus:ring-1 focus:ring-sanaa-indigo" />
                                </div>
                            @endif
                        </div>
                    @else
                        <div class="flex flex-col items-center justify-center py-12 text-gray-500">
                            <x-heroicon-o-cog-6-tooth class="w-10 h-10 mb-3 opacity-30" />
                            <p class="text-sm">Step Configuration</p>
                            <p class="text-xs mt-1">Select a step to configure its parameters</p>
                        </div>
                    @endif
                </div>
            </div>
        </div>

        {{-- ── YAML Preview Panel ──────────────────────────────────────── --}}
        @if ($showYamlPreview)
            <div class="glass-dark rounded-xl p-6">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-sm font-semibold text-gray-300 flex items-center gap-2">
                        <x-heroicon-o-code-bracket class="w-4 h-4 text-sanaa-purple" />
                        Generated YAML
                    </h3>
                    <button wire:click="$set('showYamlPreview', false)" class="p-1 text-gray-500 hover:text-white">
                        <x-heroicon-o-x-mark class="w-4 h-4" />
                    </button>
                </div>
                <pre class="text-xs overflow-auto max-h-[30rem] bg-gray-950 text-green-300 p-4 rounded-lg border border-gray-700/50 font-mono">{{ $generatedYaml }}</pre>
            </div>
        @endif
    </div>
</x-filament-panels::page>
