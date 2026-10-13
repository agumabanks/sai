<x-filament-panels::page>

    <style>
        .sanaa-command-shell {
            background: linear-gradient(135deg, #0f172a 0%, #111827 58%, #0b1120 100%);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 28px;
            box-shadow: 0 24px 80px rgba(15, 23, 42, 0.18);
            overflow: hidden;
        }

        .sanaa-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.05);
            color: #ccfbf1;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.24em;
            text-transform: uppercase;
        }

        .sanaa-tab-group {
            display: inline-flex;
            gap: 0.25rem;
            padding: 0.25rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .sanaa-tab {
            border: 0;
            background: transparent;
            border-radius: 14px;
            padding: 0.7rem 1rem;
            color: #cbd5e1;
            font-size: 0.92rem;
            font-weight: 600;
            transition: all 160ms ease;
        }

        .sanaa-tab:hover {
            color: #ffffff;
        }

        .sanaa-tab.is-active {
            background: #f8fafc;
            color: #0f172a;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18);
        }

        .sanaa-surface {
            background: #111827;
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 26px;
            color: #e5e7eb;
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
        }

        .sanaa-surface-soft {
            background: linear-gradient(160deg, rgba(20, 184, 166, 0.12), rgba(15, 23, 42, 0.92) 48%, rgba(15, 23, 42, 0.98));
            border: 1px solid rgba(94, 234, 212, 0.18);
        }

        .sanaa-metric-card {
            border-radius: 24px;
            border: 1px solid rgba(148, 163, 184, 0.24);
            padding: 1.2rem 1.35rem;
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.1);
        }

        .sanaa-metric-card h3 {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.24em;
            margin: 0;
            text-transform: uppercase;
        }

        .sanaa-metric-card p {
            font-size: 2rem;
            font-weight: 700;
            margin: 0.55rem 0 0;
            line-height: 1;
        }

        .sanaa-metric-dark {
            background: #0b1120;
            border-color: rgba(148, 163, 184, 0.28);
            color: #f8fafc;
        }

        .sanaa-metric-mint {
            background: #ecfdf5;
            border-color: #a7f3d0;
            color: #065f46;
        }

        .sanaa-metric-amber {
            background: #fffbeb;
            border-color: #fcd34d;
            color: #b45309;
        }

        .sanaa-grid-tight {
            display: grid;
            gap: 1rem;
        }

        .sanaa-action-button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 18px;
            padding: 0.95rem 1.2rem;
            font-size: 0.95rem;
            font-weight: 700;
            transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
            border: 1px solid transparent;
        }

        .sanaa-action-button:hover {
            transform: translateY(-1px);
        }

        .sanaa-action-primary {
            background: linear-gradient(135deg, #312e81, #4f46e5);
            color: #ffffff;
            box-shadow: 0 18px 35px rgba(79, 70, 229, 0.22);
        }

        .sanaa-action-secondary {
            background: #0f172a;
            border-color: rgba(148, 163, 184, 0.24);
            color: #ffffff;
        }

        .sanaa-filter-shell {
            background: #0f172a;
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 24px;
            color: #e5e7eb;
        }

        .sanaa-field {
            width: 100%;
            min-width: 220px;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.28);
            background: #020617;
            color: #e5e7eb;
            padding: 0.75rem 0.95rem;
            font-size: 0.95rem;
        }

        .sanaa-card-button {
            width: 100%;
            border-radius: 24px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: #0f172a;
            color: #e5e7eb;
            padding: 1rem;
            text-align: left;
            box-shadow: 0 14px 30px rgba(15, 23, 42, 0.12);
            transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
        }

        .sanaa-card-button:hover {
            transform: translateY(-2px);
            border-color: rgba(148, 163, 184, 0.34);
            box-shadow: 0 20px 38px rgba(15, 23, 42, 0.18);
        }

        .sanaa-card-title {
            color: #f8fafc;
            font-size: 0.95rem;
            font-weight: 700;
        }

        .sanaa-card-subtitle {
            color: #94a3b8;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }

        .sanaa-card-body {
            color: #cbd5e1;
            font-size: 0.92rem;
            line-height: 1.7;
        }

        .sanaa-icon-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 44px;
            height: 44px;
            border-radius: 18px;
            background: #1e293b;
            color: #ffffff;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.12);
            font-size: 1.1rem;
        }

        .sanaa-run-chip {
            border-radius: 9999px;
            padding: 0.3rem 0.7rem;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(148, 163, 184, 0.16);
            color: #cbd5e1;
            font-size: 11px;
            font-weight: 700;
        }

        @media (min-width: 1280px) {
            .sanaa-ops-grid {
                display: grid;
                gap: 1rem;
                grid-template-columns: minmax(0, 1.35fr) minmax(0, 0.95fr);
            }
        }

        @media (min-width: 640px) {
            .sanaa-metrics-grid {
                display: grid;
                gap: 1rem;
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (min-width: 1024px) {
            .sanaa-featured-grid,
            .sanaa-quick-grid {
                display: grid;
                gap: 1rem;
                grid-template-columns: repeat(4, minmax(0, 1fr));
            }
        }

        @media (min-width: 768px) and (max-width: 1023px) {
            .sanaa-featured-grid,
            .sanaa-quick-grid {
                display: grid;
                gap: 1rem;
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
    </style>

    {{-- ─── Header with Tab Navigation ──────────────────────────────────────── --}}
    <div class="sanaa-command-shell mb-6">
        <div class="flex flex-col gap-5 px-6 py-6 lg:flex-row lg:items-end lg:justify-between lg:px-8">
            <div class="space-y-4">
                <div class="sanaa-kicker">
                    Sanaa Operations Hub
                </div>
                <div>
                    <h1 class="text-2xl font-semibold tracking-tight text-white sm:text-3xl">Skills Command Center</h1>
                    <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                        Run Sanaa Doctor, tenant syncs, and ecosystem-aware skills from one cockpit built for the way the Sanaa stack actually operates.
                    </p>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                    <div class="sanaa-tab-group">
                        <button
                            wire:click="switchTab('catalog')"
                            class="sanaa-tab {{ $activeTab === 'catalog' ? 'is-active' : '' }}"
                        >
                            Skills Catalog
                        </button>
                        <button
                            wire:click="switchTab('intelligence')"
                            class="sanaa-tab {{ $activeTab === 'intelligence' ? 'is-active' : '' }}"
                        >
                            ML Intelligence
                        </button>
                    </div>
                    <p class="text-sm text-slate-300/90">
                        {{ count($skills) }} skills live · {{ count($this->getCategories()) }} categories
                    </p>
                </div>
            </div>
            <div class="flex flex-wrap gap-2">
                <x-filament::button color="gray" size="sm" wire:click="refreshData">
                    <x-filament::loading-indicator wire:loading wire:target="refreshData" class="mr-1 h-4 w-4" />
                    Refresh
                </x-filament::button>
                @if ($activeTab === 'intelligence')
                    <x-filament::button color="warning" size="sm" wire:click="triggerMLAnalysis">
                        <x-filament::loading-indicator wire:loading wire:target="triggerMLAnalysis" class="mr-1 h-4 w-4" />
                        Run ML Analysis
                    </x-filament::button>
                @endif
                <x-filament::button color="gray" size="sm" wire:click="loadRecentRuns">
                    Recent Runs
                </x-filament::button>
                <x-filament::button color="primary" size="sm" wire:click="$set('showCreatePanel', true)">
                    + Create New Skill
                </x-filament::button>
            </div>
        </div>
    </div>

    @if ($loadError)
        <div class="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
            Skill catalog loaded with fallback data. Engine response: {{ $loadError }}
        </div>
    @endif

    {{-- ═══ ML INTELLIGENCE TAB ═══════════════════════════════════════════════ --}}
    @if ($activeTab === 'intelligence')
        <div class="space-y-6">

            {{-- ML Performance Scoreboard --}}
            <div class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
                <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
                    <h2 class="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Skill Performance Scoreboard
                    </h2>
                    <p class="text-xs text-gray-400 mt-0.5">ML-computed composite scores from success rates, latency, user feedback, and trends</p>
                </div>

                @if (count($mlScores) > 0)
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <thead>
                                <tr class="border-b border-gray-100 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    <th class="text-left px-5 py-3">Skill</th>
                                    <th class="text-center px-3 py-3">Score</th>
                                    <th class="text-center px-3 py-3">Trend</th>
                                    <th class="text-center px-3 py-3">Success Rate</th>
                                    <th class="text-center px-3 py-3">Avg Latency</th>
                                    <th class="text-center px-3 py-3">Total Runs</th>
                                    <th class="text-center px-3 py-3">User Rating</th>
                                    <th class="text-center px-3 py-3">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-50 dark:divide-gray-700/50">
                                @foreach ($mlScores as $name => $score)
                                    @php
                                        $perf = $score['performance_score'] ?? 0;
                                        $color = $this->getScoreColor($perf);
                                        $trend = $score['trend'] ?? 'stable';
                                    @endphp
                                    <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                                        <td class="px-5 py-3">
                                            <button wire:click="selectSkill('{{ $name }}')" class="font-medium text-primary-600 dark:text-primary-400 hover:underline">
                                                {{ $name }}
                                            </button>
                                        </td>
                                        <td class="text-center px-3 py-3">
                                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold
                                                bg-{{ $color }}-100 text-{{ $color }}-700 dark:bg-{{ $color }}-900/30 dark:text-{{ $color }}-300">
                                                {{ number_format($perf * 100, 0) }}%
                                            </span>
                                        </td>
                                        <td class="text-center px-3 py-3">
                                            <span class="text-sm {{ $trend === 'improving' ? 'text-emerald-500' : ($trend === 'degrading' ? 'text-rose-500' : 'text-gray-400') }}">
                                                {{ $this->getTrendIcon($trend) }} {{ ucfirst($trend) }}
                                            </span>
                                        </td>
                                        <td class="text-center px-3 py-3 font-mono text-xs">
                                            {{ number_format(($score['success_rate'] ?? 0) * 100, 1) }}%
                                        </td>
                                        <td class="text-center px-3 py-3 font-mono text-xs">
                                            {{ number_format($score['avg_duration_ms'] ?? 0, 0) }}ms
                                        </td>
                                        <td class="text-center px-3 py-3 font-mono text-xs">
                                            {{ $score['total_runs'] ?? 0 }}
                                        </td>
                                        <td class="text-center px-3 py-3">
                                            @if (($score['avg_user_rating'] ?? null) !== null)
                                                <span class="text-xs">{{ number_format($score['avg_user_rating'], 1) }}/5</span>
                                            @else
                                                <span class="text-xs text-gray-400">--</span>
                                            @endif
                                        </td>
                                        <td class="text-center px-3 py-3">
                                            <div class="flex items-center justify-center gap-1">
                                                <button wire:click="submitFeedback('{{ $name }}', 1)" class="p-1 rounded hover:bg-emerald-50 dark:hover:bg-emerald-900/20 text-gray-400 hover:text-emerald-500 transition" title="Thumbs up">
                                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"/></svg>
                                                </button>
                                                <button wire:click="submitFeedback('{{ $name }}', -1)" class="p-1 rounded hover:bg-rose-50 dark:hover:bg-rose-900/20 text-gray-400 hover:text-rose-500 transition" title="Thumbs down">
                                                    <svg class="w-4 h-4 rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"/></svg>
                                                </button>
                                                <button wire:click="loadSkillML('{{ $name }}')" class="p-1 rounded hover:bg-sky-50 dark:hover:bg-sky-900/20 text-gray-400 hover:text-sky-500 transition" title="View ML details">
                                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                @endforeach
                            </tbody>
                        </table>
                    </div>
                @else
                    <div class="px-5 py-10 text-center text-gray-400 text-sm">
                        <div class="text-3xl mb-2">&#129302;</div>
                        No ML data yet. Click <strong>Run ML Analysis</strong> to aggregate metrics from skill runs.
                    </div>
                @endif
            </div>

            {{-- Skill ML Detail Panel --}}
            @if (!empty($skillMLData) && ($skillMLData['performance_score'] ?? null) !== null)
                @php
                    $mlSkill = $skillMLData['skill_name'] ?? '';
                    $mlScore = $skillMLData['performance_score'] ?? 0;
                    $mlColor = $this->getScoreColor($mlScore);
                @endphp
                <div class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
                    <div class="flex items-center justify-between mb-4">
                        <div>
                            <h3 class="text-lg font-semibold">{{ $mlSkill }} — ML Deep Dive</h3>
                            <p class="text-xs text-gray-400">Detailed performance analysis, learned parameters, and improvement history</p>
                        </div>
                        <x-filament::button size="xs" color="gray" wire:click="$set('skillMLData', [])">Dismiss</x-filament::button>
                    </div>

                    <div class="grid gap-4 sm:grid-cols-4 mb-6">
                        <div class="rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-4 text-center">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-gray-400">Performance</div>
                            <div class="mt-2 text-2xl font-bold text-{{ $mlColor }}-600 dark:text-{{ $mlColor }}-400">{{ number_format($mlScore * 100, 0) }}%</div>
                        </div>
                        <div class="rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-4 text-center">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-gray-400">Success Rate</div>
                            <div class="mt-2 text-2xl font-bold">{{ number_format(($skillMLData['success_rate'] ?? 0) * 100, 1) }}%</div>
                        </div>
                        <div class="rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-4 text-center">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-gray-400">Avg Latency</div>
                            <div class="mt-2 text-2xl font-bold">{{ number_format($skillMLData['avg_duration_ms'] ?? 0, 0) }}ms</div>
                        </div>
                        <div class="rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-4 text-center">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-gray-400">Trend</div>
                            <div class="mt-2 text-2xl font-bold {{ ($skillMLData['trend'] ?? '') === 'improving' ? 'text-emerald-500' : (($skillMLData['trend'] ?? '') === 'degrading' ? 'text-rose-500' : 'text-gray-500') }}">
                                {{ $this->getTrendIcon($skillMLData['trend'] ?? 'stable') }} {{ ucfirst($skillMLData['trend'] ?? 'stable') }}
                            </div>
                        </div>
                    </div>

                    {{-- Performance History Chart (ASCII/visual) --}}
                    @if (!empty($skillMLData['history']))
                        <div class="mb-6">
                            <h4 class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Performance History (7-day)</h4>
                            <div class="flex items-end gap-1 h-20">
                                @foreach ($skillMLData['history'] as $h)
                                    @php
                                        $barHeight = max(4, ($h['score'] ?? 0) * 80);
                                        $barColor = $this->getScoreColor($h['score'] ?? 0);
                                    @endphp
                                    <div class="flex-1 flex flex-col items-center gap-1">
                                        <div class="w-full rounded-t bg-{{ $barColor }}-500/80 transition-all" style="height: {{ $barHeight }}px" title="{{ $h['date'] ?? '' }}: {{ number_format(($h['score'] ?? 0) * 100, 0) }}%"></div>
                                        <span class="text-[9px] text-gray-400">{{ \Illuminate\Support\Str::substr($h['date'] ?? '', 5, 5) }}</span>
                                    </div>
                                @endforeach
                            </div>
                        </div>
                    @endif

                    {{-- Error Categories --}}
                    @if (!empty($skillMLData['error_categories']))
                        <div class="mb-6">
                            <h4 class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Error Classification</h4>
                            <div class="flex flex-wrap gap-2">
                                @foreach ($skillMLData['error_categories'] as $cat => $count)
                                    <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">
                                        {{ $cat }}: {{ $count }}
                                    </span>
                                @endforeach
                            </div>
                        </div>
                    @endif

                    {{-- Learned Parameters --}}
                    @if (!empty($skillMLData['parameter_insights']))
                        <div class="mb-6">
                            <h4 class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Learned Optimal Parameters</h4>
                            <div class="grid gap-3 sm:grid-cols-2">
                                @foreach ($skillMLData['parameter_insights'] as $pi)
                                    <div class="rounded-lg border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-3">
                                        <div class="flex items-center justify-between">
                                            <span class="font-mono text-sm font-semibold">{{ $pi['parameter'] }}</span>
                                            <span class="text-xs text-gray-400">{{ $pi['sample_size'] }} samples</span>
                                        </div>
                                        <div class="mt-1 text-sm">
                                            Optimal: <span class="font-bold text-primary-600 dark:text-primary-400">{{ $pi['optimal_value'] }}</span>
                                        </div>
                                        <div class="mt-1 text-xs text-gray-400">
                                            Success correlation: {{ number_format($pi['success_correlation'] * 100, 1) }}%
                                        </div>
                                        @if (!empty($pi['distribution']))
                                            <div class="mt-2 flex flex-wrap gap-1">
                                                @foreach (array_slice($pi['distribution'], 0, 5) as $val => $cnt)
                                                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400">{{ $val }}: {{ $cnt }}</span>
                                                @endforeach
                                            </div>
                                        @endif
                                    </div>
                                @endforeach
                            </div>
                        </div>
                    @endif

                    {{-- Learning Events --}}
                    @if (!empty($skillMLData['learning_events']))
                        <div>
                            <h4 class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">Learning Timeline</h4>
                            <div class="space-y-2">
                                @foreach ($skillMLData['learning_events'] as $le)
                                    @php
                                        $leColor = match($le['impact'] ?? 'low') {
                                            'high' => 'rose',
                                            'medium' => 'amber',
                                            default => 'gray',
                                        };
                                    @endphp
                                    <div class="flex items-start gap-3 rounded-lg border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-3">
                                        <span class="mt-0.5 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-{{ $leColor }}-100 text-{{ $leColor }}-700 dark:bg-{{ $leColor }}-900/30 dark:text-{{ $leColor }}-300">
                                            {{ $le['event_type'] ?? '' }}
                                        </span>
                                        <div class="flex-1 min-w-0">
                                            <p class="text-sm text-gray-700 dark:text-gray-300">{{ $le['description'] ?? '' }}</p>
                                            <div class="mt-1 flex items-center gap-3 text-xs text-gray-400">
                                                <span>Confidence: {{ number_format(($le['confidence'] ?? 0) * 100, 0) }}%</span>
                                                <span>{{ \Illuminate\Support\Carbon::parse($le['created_at'] ?? now())->diffForHumans() }}</span>
                                                @if ($le['applied'] ?? false)
                                                    <span class="text-emerald-500 font-semibold">Applied</span>
                                                @endif
                                            </div>
                                        </div>
                                    </div>
                                @endforeach
                            </div>
                        </div>
                    @endif
                </div>
            @elseif (!empty($skillMLData) && ($skillMLData['message'] ?? ''))
                <div class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 text-center text-sm text-gray-400">
                    {{ $skillMLData['message'] }}
                </div>
            @endif

            {{-- Global Learning Log --}}
            @if (count($learningLog) > 0)
                <div class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
                    <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
                        <h2 class="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                            Global Learning Log
                        </h2>
                        <p class="text-xs text-gray-400 mt-0.5">Recent events the ML engine has detected and learned across all skills</p>
                    </div>
                    <div class="divide-y divide-gray-50 dark:divide-gray-700/50">
                        @foreach (array_slice($learningLog, 0, 15) as $event)
                            @php
                                $evColor = match($event['impact'] ?? 'low') {
                                    'high' => 'rose',
                                    'medium' => 'amber',
                                    default => 'gray',
                                };
                                $evTypeColor = match($event['event_type'] ?? '') {
                                    'anomaly_detected' => 'rose',
                                    'parameter_tuned' => 'sky',
                                    'negative_feedback' => 'amber',
                                    'improvement_applied' => 'emerald',
                                    default => 'gray',
                                };
                            @endphp
                            <div class="flex items-start gap-3 px-5 py-3">
                                <span class="mt-0.5 inline-flex items-center shrink-0 px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-{{ $evTypeColor }}-100 text-{{ $evTypeColor }}-700 dark:bg-{{ $evTypeColor }}-900/30 dark:text-{{ $evTypeColor }}-300">
                                    {{ str_replace('_', ' ', $event['event_type'] ?? '') }}
                                </span>
                                <div class="flex-1 min-w-0">
                                    <div class="flex items-center gap-2">
                                        <span class="text-xs font-semibold text-primary-600 dark:text-primary-400">{{ $event['skill_name'] ?? '' }}</span>
                                        <span class="text-[10px] text-gray-400">{{ \Illuminate\Support\Carbon::parse($event['created_at'] ?? now())->diffForHumans() }}</span>
                                    </div>
                                    <p class="mt-0.5 text-sm text-gray-600 dark:text-gray-400 truncate">{{ $event['description'] ?? '' }}</p>
                                </div>
                                <span class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-{{ $evColor }}-100 text-{{ $evColor }}-700 dark:bg-{{ $evColor }}-900/30 dark:text-{{ $evColor }}-300">
                                    {{ $event['impact'] ?? 'low' }}
                                </span>
                            </div>
                        @endforeach
                    </div>
                </div>
            @endif

        </div>
    @endif

    {{-- ═══ CATALOG TAB (original content) ════════════════════════════════════ --}}
    @if ($activeTab === 'catalog')

    <div class="sanaa-ops-grid mb-6">
        <div class="sanaa-surface sanaa-surface-soft p-6">
            <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                <div class="max-w-2xl">
                    <div class="inline-flex items-center gap-2 rounded-full border border-emerald-300/30 bg-emerald-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-emerald-200">
                        Estate Control
                    </div>
                    <h2 class="mt-4 text-2xl font-semibold tracking-tight text-white">Operator flow built around Sanaa Doctor and tenant sync</h2>
                    <p class="mt-3 text-sm leading-6 text-slate-300">
                        Start with the doctor briefing, confirm drift and risk, then push the clean fix outward. This layout puts the Sanaa ecosystem flow ahead of the raw skill list.
                    </p>
                </div>
                <div class="flex flex-wrap gap-3">
                    <button
                        type="button"
                        wire:click="runQuickAction('sanaa_doctor')"
                        class="sanaa-action-button sanaa-action-primary"
                    >
                        Run Doctor Briefing
                    </button>
                    <button
                        type="button"
                        wire:click="runQuickAction('tenant_sync_status')"
                        class="sanaa-action-button sanaa-action-secondary"
                    >
                        Check Tenant Sync
                    </button>
                </div>
            </div>
        </div>

        <div class="sanaa-metrics-grid sanaa-grid-tight">
            @foreach ($this->getCatalogSnapshot() as $item)
                @php
                    $tone = match($item['tone']) {
                        'emerald' => 'sanaa-metric-card sanaa-metric-mint',
                        'amber' => 'sanaa-metric-card sanaa-metric-amber',
                        default => 'sanaa-metric-card sanaa-metric-dark',
                    };
                @endphp
                <div class="{{ $tone }}">
                    <h3>{{ $item['label'] }}</h3>
                    <p>{{ $item['value'] }}</p>
                </div>
            @endforeach
        </div>
    </div>

    @if (count($this->getFeaturedSkills()))
        <div class="sanaa-surface mb-6 p-6">
            <div class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                    <h2 class="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">Featured Operator Skills</h2>
                    <p class="mt-1 text-sm text-slate-400">The most important controls for day-to-day Sanaa estate management.</p>
                </div>
            </div>
            <div class="sanaa-featured-grid sanaa-grid-tight">
                @foreach ($this->getFeaturedSkills() as $featured)
                    @php
                        $fName = $featured['name'] ?? '';
                        $fCategory = $featured['category'] ?? 'system';
                        $fMl = $mlScores[$fName] ?? null;
                    @endphp
                    <button
                        type="button"
                        wire:click="selectSkill('{{ $fName }}')"
                        class="sanaa-card-button"
                    >
                        <div class="flex items-start justify-between gap-3">
                            <div>
                                <div class="sanaa-card-title">{{ $fName }}</div>
                                <div class="sanaa-card-subtitle mt-1">{{ $fCategory }}</div>
                            </div>
                            @if ($fMl)
                                <span class="sanaa-run-chip">
                                    {{ number_format(($fMl['performance_score'] ?? 0) * 100, 0) }}%
                                </span>
                            @endif
                        </div>
                        <p class="sanaa-card-body mt-4">{{ $featured['description'] ?? '' }}</p>
                        <div class="mt-4 text-sm font-medium text-cyan-300">Open skill workspace</div>
                    </button>
                @endforeach
            </div>
        </div>
    @endif

    {{-- ─── Filters ─────────────────────────────────────────────────────────── --}}
    <div class="sanaa-filter-shell mb-6 p-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
                <h2 class="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">Skill Catalog</h2>
                <p class="mt-1 text-sm text-slate-400">Filter, inspect, and run every registered skill without losing sight of the ops-critical ones.</p>
            </div>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
                <input
                    type="text"
                    wire:model.live.debounce.300ms="searchFilter"
                    placeholder="Search skills, tags, and descriptions"
                    class="sanaa-field"
                />
                <select
                    wire:model.live="categoryFilter"
                    class="sanaa-field"
                >
                    <option value="">All Categories</option>
                    @foreach ($this->getCategories() as $cat)
                        <option value="{{ $cat }}">{{ ucfirst($cat) }}</option>
                    @endforeach
                </select>
            </div>
        </div>
    </div>

    {{-- ─── Skill Cards Grid ────────────────────────────────────────────────── --}}
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        @forelse ($this->getFilteredSkills() as $skill)
            @php
                $sName      = $skill['name'] ?? '';
                $isEnabled  = ($skill['enabled'] ?? true) !== false;
                $isSelected = ($selectedSkill['name'] ?? null) === $sName;
                $category   = $skill['category'] ?? 'system';
                $version    = $skill['version'] ?? '1.0.0';
                $tags       = $skill['tags'] ?? [];
                $needsApproval = $skill['requires_approval'] ?? false;
            @endphp
            <div
                wire:key="skill-card-{{ $sName }}"
                class="relative flex flex-col rounded-xl border transition-all duration-150 cursor-pointer
                    {{ $isSelected
                        ? 'border-primary-500 ring-2 ring-primary-500/30 bg-primary-50 dark:bg-primary-950/20'
                        : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-primary-400' }}"
                wire:click="selectSkill('{{ $sName }}')"
            >
                {{-- Top bar --}}
                <div class="flex items-start justify-between p-4">
                    <div class="flex items-center gap-2 min-w-0">
                        {{-- Category colour dot --}}
                        <span class="inline-flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0
                            {{ match($category) {
                                'development'   => 'bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300',
                                'monitoring'    => 'bg-green-100 text-green-600 dark:bg-green-900/40 dark:text-green-300',
                                'communication' => 'bg-purple-100 text-purple-600 dark:bg-purple-900/40 dark:text-purple-300',
                                'productivity'  => 'bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-300',
                                'research'      => 'bg-sky-100 text-sky-600 dark:bg-sky-900/40 dark:text-sky-300',
                                'meta'          => 'bg-fuchsia-100 text-fuchsia-600 dark:bg-fuchsia-900/40 dark:text-fuchsia-300',
                                default         => 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
                            } }}">
                            {{ match($category) {
                                'development'   => '💻',
                                'monitoring'    => '📡',
                                'communication' => '📨',
                                'productivity'  => '📋',
                                'research'      => '🔍',
                                'meta'          => '🧠',
                                'system'        => '⚙️',
                                default         => '⚡',
                            } }}
                        </span>
                        <div class="min-w-0">
                            <div class="font-semibold text-sm truncate">{{ $sName }}</div>
                            <div class="text-xs text-gray-400">v{{ $version }} · {{ $category }}</div>
                        </div>
                    </div>
                    {{-- ML Score + Enabled toggle --}}
                    <div class="flex items-center gap-2 flex-shrink-0 ml-2">
                        @php $mlInfo = $mlScores[$sName] ?? null; @endphp
                        @if ($mlInfo)
                            @php
                                $mlPerf = $mlInfo['performance_score'] ?? 0;
                                $mlC = $mlPerf >= 0.8 ? 'emerald' : ($mlPerf >= 0.6 ? 'sky' : ($mlPerf >= 0.4 ? 'amber' : 'rose'));
                                $mlTrend = $mlInfo['trend'] ?? 'stable';
                            @endphp
                            <span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-{{ $mlC }}-100 text-{{ $mlC }}-700 dark:bg-{{ $mlC }}-900/30 dark:text-{{ $mlC }}-300" title="ML Score: {{ number_format($mlPerf * 100, 0) }}%">
                                {{ number_format($mlPerf * 100, 0) }}%
                                <span class="{{ $mlTrend === 'improving' ? 'text-emerald-500' : ($mlTrend === 'degrading' ? 'text-rose-500' : '') }}">
                                    {{ $mlTrend === 'improving' ? '↗' : ($mlTrend === 'degrading' ? '↘' : '→') }}
                                </span>
                            </span>
                        @endif
                        @if ($needsApproval)
                            <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                                approval
                            </span>
                        @endif
                        <button
                            type="button"
                            wire:click.stop="toggleSkill('{{ $sName }}', {{ $isEnabled ? 'false' : 'true' }})"
                            title="{{ $isEnabled ? 'Disable' : 'Enable' }} skill"
                            class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none
                                {{ $isEnabled ? 'bg-primary-500' : 'bg-gray-300 dark:bg-gray-600' }}"
                        >
                            <span class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform
                                {{ $isEnabled ? 'translate-x-4' : 'translate-x-1' }}">
                            </span>
                        </button>
                    </div>
                </div>

                {{-- Description --}}
                <div class="px-4 pb-2 flex-1">
                    <p class="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                        {{ $skill['description'] ?? '' }}
                    </p>
                </div>

                {{-- Tags --}}
                @if (count($tags))
                    <div class="px-4 pb-3 flex flex-wrap gap-1">
                        @foreach (array_slice($tags, 0, 5) as $tag)
                            <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                                {{ $tag }}
                            </span>
                        @endforeach
                    </div>
                @endif

                {{-- Footer actions --}}
                <div class="border-t border-gray-100 dark:border-gray-700 px-4 py-2 flex items-center justify-between">
                    <x-filament::button
                        size="xs"
                        color="primary"
                        wire:click.stop="selectSkill('{{ $sName }}')"
                    >
                        Select & Run
                    </x-filament::button>
                    <x-filament::button
                        size="xs"
                        color="gray"
                        wire:click.stop="hotReload('{{ $sName }}')"
                        title="Hot-reload this skill into the live registry"
                    >
                        ↻ Reload
                    </x-filament::button>
                </div>
            </div>
        @empty
            <div class="col-span-3 py-12 text-center text-gray-400">
                <div class="text-4xl mb-3">⚡</div>
                <div class="text-sm">No skills found. Try refreshing or adjusting the filter.</div>
            </div>
        @endforelse
    </div>

    {{-- ─── Quick-Action Shortcuts ──────────────────────────────────────────── --}}
    <div class="mt-6">
        <div class="sanaa-surface p-6">
            <div class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                    <h2 class="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">Quick Actions</h2>
                    <p class="mt-1 text-sm text-slate-400">Fast-launch the routines we keep coming back to across the Sanaa ecosystem.</p>
                </div>
            </div>
            <div class="sanaa-quick-grid sanaa-grid-tight">
                @foreach ($this->getQuickActions() as $actionKey => $action)
                    <button
                        type="button"
                        wire:click="runQuickAction('{{ $actionKey }}')"
                        class="sanaa-card-button"
                    >
                        <div class="flex items-start justify-between gap-3">
                            <div class="flex items-center gap-3">
                                <div class="sanaa-icon-chip">
                                    {{ $action['icon'] }}
                                </div>
                                <div>
                                    <div class="sanaa-card-title">{{ $action['label'] }}</div>
                                    <div class="sanaa-card-subtitle mt-1">{{ $action['skill'] }}</div>
                                </div>
                            </div>
                            <span class="sanaa-run-chip">
                                Run
                            </span>
                        </div>
                        <p class="sanaa-card-body mt-4">{{ $action['description'] ?? 'Open a prepared skill action.' }}</p>
                    </button>
                @endforeach
            </div>
        </div>
    </div>

    {{-- ─── Create New Skill ────────────────────────────────────────────────── --}}
    @if ($showCreatePanel)
        <div class="mt-6">
            <x-filament::card>
                <div class="flex items-center justify-between mb-4">
                    <div>
                        <h2 class="text-base font-semibold">🧠 Create New Skill (AI-Generated)</h2>
                        <p class="text-xs text-gray-500 mt-0.5">
                            Describe what the skill should do — the Brain will write the Python code and manifest, then hot-reload it instantly.
                        </p>
                    </div>
                    <x-filament::button size="sm" color="gray" wire:click="$set('showCreatePanel', false)">✕</x-filament::button>
                </div>

                <div class="grid gap-4 lg:grid-cols-2">
                    <div>
                        <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                            Skill Name <span class="text-gray-400">(snake_case)</span>
                        </label>
                        <input
                            type="text"
                            wire:model="newSkillName"
                            placeholder="e.g. binance_price"
                            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                            Description <span class="text-gray-400">(natural language)</span>
                        </label>
                        <textarea
                            wire:model="newSkillDescription"
                            rows="2"
                            placeholder="Fetch the current Bitcoin price from Binance and return it in USD and UGX."
                            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
                        ></textarea>
                    </div>
                </div>

                <div class="mt-4 flex items-center gap-3">
                    <x-filament::button
                        wire:click="createSkill"
                        wire:loading.attr="disabled"
                        wire:target="createSkill"
                        color="primary"
                    >
                        <x-filament::loading-indicator wire:loading wire:target="createSkill" class="mr-1 h-4 w-4" />
                        {{ $isRunning ? 'Generating…' : '🚀 Generate & Load Skill' }}
                    </x-filament::button>
                    <span class="text-xs text-gray-400">This may take 10–20 seconds while the Brain writes the code.</span>
                </div>
            </x-filament::card>
        </div>
    @endif

    {{-- ─── Recent Skill Runs ───────────────────────────────────────────────── --}}
    @if ($runsOutput)
        <div class="mt-6">
            <x-filament::card>
                <div class="flex items-center justify-between mb-3">
                    <h2 class="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Recent Skill Runs</h2>
                    <x-filament::button size="xs" color="gray" wire:click="$set('runsOutput', '')">✕ Clear</x-filament::button>
                </div>
                <pre class="rounded-lg bg-gray-950 text-green-200 p-4 text-xs overflow-auto max-h-72 font-mono">{{ $runsOutput }}</pre>
            </x-filament::card>
        </div>
    @endif

    @endif {{-- End of catalog/intelligence tab --}}

    {{-- ═══ SKILL WORKSPACE MODAL ═════════════════════════════════════════════ --}}
    @if ($showWorkspace && $selectedSkill)
        @php
            $params   = $selectedSkill['parameters'] ?? [];
            $sName    = $selectedSkill['name'] ?? '';
            $sCat     = $selectedSkill['category'] ?? 'system';
            $sVer     = $selectedSkill['version'] ?? '1.0.0';
            $sDesc    = $selectedSkill['description'] ?? '';
            $wsML     = $mlScores[$sName] ?? null;
            $wsScore  = $wsML ? ($wsML['performance_score'] ?? 0) : null;
            $wsTrend  = $wsML ? ($wsML['trend'] ?? 'stable') : null;
            $wsColor  = $wsScore !== null ? ($wsScore >= 0.8 ? 'emerald' : ($wsScore >= 0.6 ? 'sky' : ($wsScore >= 0.4 ? 'amber' : 'rose'))) : null;
            $catEmoji = match($sCat) { 'development' => '&#x1F4BB;', 'monitoring' => '&#x1F4E1;', 'communication' => '&#x1F4E8;', 'productivity' => '&#x1F4CB;', 'research' => '&#x1F50D;', 'meta' => '&#x1F9E0;', default => '&#x2699;&#xFE0F;' };
        @endphp

        <div class="contents" x-data="{ section: 'payload' }">
        <template x-teleport="body">
            {{-- Backdrop --}}
            <div class="fixed inset-0 isolate" style="z-index: 2147483000" x-on:keydown.escape.window="$wire.closeWorkspace()">
                <div class="fixed inset-0 bg-black/70 backdrop-blur-sm" wire:click="closeWorkspace"></div>

                {{-- Modal — vertically & horizontally centred --}}
                <div class="fixed inset-0 flex items-center justify-center p-4 sm:p-8" style="z-index: 2147483001">
                    <div
                        class="relative flex w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0b0f1a] shadow-2xl"
                        style="max-height: min(88vh, 860px)"
                        wire:click.stop
                    >

                        {{-- ── Top bar ─────────────────────────────────────── --}}
                        <header class="flex shrink-0 items-center justify-between gap-4 border-b border-white/[0.06] px-7 py-5">
                            <div class="flex items-center gap-4 min-w-0">
                                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.06] text-lg">{!! $catEmoji !!}</div>
                                <div class="min-w-0">
                                    <h2 class="truncate text-[15px] font-semibold tracking-tight text-white">{{ $sName }}</h2>
                                    <p class="mt-0.5 text-xs text-white/40">{{ ucfirst($sCat) }} &middot; v{{ $sVer }}
                                        @if ($wsScore !== null)
                                            &middot;
                                            <span class="text-{{ $wsColor }}-400 font-medium">{{ number_format($wsScore * 100, 0) }}%</span>
                                            <span class="text-white/30">{{ $wsTrend === 'improving' ? '&#8599;' : ($wsTrend === 'degrading' ? '&#8600;' : '&#8594;') }}</span>
                                        @endif
                                    </p>
                                </div>
                            </div>

                            <div class="flex items-center gap-2 shrink-0">
                                <button wire:click="hotReload('{{ $sName }}')" class="rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-white/60 transition hover:bg-white/[0.08] hover:text-white">Reload</button>
                                <button wire:click="runSelectedSkill" wire:loading.attr="disabled" wire:target="runSelectedSkill"
                                    class="rounded-lg bg-indigo-500 px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:bg-indigo-400 disabled:opacity-50">
                                    <span wire:loading.remove wire:target="runSelectedSkill">Run</span>
                                    <span wire:loading wire:target="runSelectedSkill">Running&hellip;</span>
                                </button>
                                <button wire:click="clearSelection" class="ml-1 rounded-lg p-1.5 text-white/30 transition hover:bg-white/[0.06] hover:text-white/70" title="Close">
                                    <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                                </button>
                            </div>
                        </header>

                        {{-- ── Description --}}
                        @if ($sDesc)
                            <div class="shrink-0 border-b border-white/[0.04] px-7 py-4">
                                <p class="text-sm leading-relaxed text-white/50">{{ $sDesc }}</p>
                            </div>
                        @endif

                        {{-- ── Section tabs ─────────────────────────────────── --}}
                        <nav class="flex shrink-0 gap-0 border-b border-white/[0.06] px-7">
                            @foreach (['payload' => 'Payload', 'parameters' => 'Parameters', 'output' => 'Output'] as $tabKey => $tabLabel)
                                <button
                                    type="button"
                                    @click="section = '{{ $tabKey }}'"
                                    class="relative px-4 py-3 text-xs font-semibold tracking-wide transition"
                                    :class="section === '{{ $tabKey }}'
                                        ? 'text-white'
                                        : 'text-white/35 hover:text-white/60'"
                                >
                                    {{ $tabLabel }}
                                    @if ($tabKey === 'output' && $skillOutput)
                                        <span class="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                                    @endif
                                    <span
                                        class="absolute inset-x-0 -bottom-px h-[2px] rounded-full bg-indigo-400 transition-opacity"
                                        :class="section === '{{ $tabKey }}' ? 'opacity-100' : 'opacity-0'"
                                    ></span>
                                </button>
                            @endforeach
                        </nav>

                        {{-- ── Content area (scrollable) ────────────────────── --}}
                        <div class="min-h-0 flex-1 overflow-y-auto" style="overscroll-behavior: contain">

                            {{-- PAYLOAD ------------------------------------------------- --}}
                            <div x-show="section === 'payload'" x-cloak class="p-7">
                                <textarea
                                    wire:model="skillArgs"
                                    class="w-full rounded-xl border border-white/[0.08] bg-[#060a14] px-5 py-4 font-mono text-[13px] leading-6 text-cyan-50 placeholder-white/20 transition focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                                    rows="10"
                                    spellcheck="false"
                                    placeholder='{ "action": "overview" }'
                                ></textarea>
                            </div>

                            {{-- PARAMETERS ---------------------------------------------- --}}
                            <div x-show="section === 'parameters'" x-cloak class="p-7">
                                @if (count($params))
                                    <div class="space-y-3">
                                        @foreach ($params as $pName => $pSchema)
                                            <div class="rounded-xl border border-white/[0.06] bg-white/[0.02] px-5 py-4">
                                                <div class="flex flex-wrap items-center gap-2">
                                                    <span class="font-mono text-sm font-semibold text-white">{{ $pName }}</span>
                                                    <span class="rounded-md bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-300/80">{{ $pSchema['type'] ?? 'string' }}</span>
                                                    @if ($pSchema['required'] ?? false)
                                                        <span class="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300/80">Required</span>
                                                    @endif
                                                </div>
                                                @if (!empty($pSchema['description']))
                                                    <p class="mt-2 text-sm leading-relaxed text-white/40">{{ $pSchema['description'] }}</p>
                                                @endif
                                                @if (!empty($pSchema['enum']))
                                                    <div class="mt-3 flex flex-wrap gap-1.5">
                                                        @foreach ($pSchema['enum'] as $option)
                                                            <span class="rounded-md bg-white/[0.05] px-2 py-0.5 text-xs text-amber-200/70">{{ $option }}</span>
                                                        @endforeach
                                                    </div>
                                                @endif
                                            </div>
                                        @endforeach
                                    </div>
                                @else
                                    <div class="rounded-xl border border-dashed border-white/[0.08] px-6 py-12 text-center text-sm text-white/30">
                                        No parameters defined. Send a raw JSON payload.
                                    </div>
                                @endif
                            </div>

                            {{-- OUTPUT -------------------------------------------------- --}}
                            <div x-show="section === 'output'" x-cloak class="p-7">
                                @if ($skillOutput)
                                    <pre class="max-h-[50vh] overflow-auto rounded-xl border border-white/[0.06] bg-[#060a14] p-5 font-mono text-xs leading-6 text-emerald-200/90 selection:bg-emerald-500/30">{{ $skillOutput }}</pre>

                                    <div class="mt-5 flex items-center gap-3">
                                        <span class="text-xs font-medium text-white/25">Was this helpful?</span>
                                        <button wire:click="submitFeedback('{{ $sName }}', 1)"
                                            class="group flex items-center gap-1.5 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-xs text-white/40 transition hover:border-emerald-500/30 hover:text-emerald-400">
                                            <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"/></svg>
                                            Yes
                                        </button>
                                        <button wire:click="submitFeedback('{{ $sName }}', -1)"
                                            class="group flex items-center gap-1.5 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-xs text-white/40 transition hover:border-rose-500/30 hover:text-rose-400">
                                            <svg class="h-3.5 w-3.5 rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"/></svg>
                                            No
                                        </button>
                                    </div>
                                @else
                                    <div class="flex flex-col items-center justify-center rounded-xl border border-dashed border-white/[0.06] px-6 py-16 text-center">
                                        <div class="text-white/15 text-3xl mb-3">&#9654;</div>
                                        <p class="text-sm text-white/25">Hit <span class="font-semibold text-white/40">Run</span> to see output here.</p>
                                    </div>
                                @endif
                            </div>
                        </div>

                    </div>
                </div>
            </div>
        </template>
        </div>
    @endif

</x-filament-panels::page>
