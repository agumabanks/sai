@php
    $preview = $this->getProvisionPreview();
    $selectedSource = $this->getSelectedSourceMeta();
    $activeTenants = $this->getActiveTenants();
    $inactiveTenants = $this->getInactiveTenants();
@endphp

<x-filament-panels::page>
    <div class="space-y-6" @if($currentRunId && $isRunning) wire:poll.visible.4s="refreshProvisionRun" @endif>
        <section class="overflow-hidden rounded-[2rem] border border-white/8 bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.18),_transparent_34%),radial-gradient(circle_at_top_right,_rgba(96,165,250,0.14),_transparent_30%),linear-gradient(135deg,_rgba(3,7,18,0.98)_0%,_rgba(8,15,33,0.96)_52%,_rgba(15,23,42,0.94)_100%)] px-6 py-7 shadow-[0_36px_120px_-52px_rgba(15,23,42,0.95)] sm:px-8">
            <div class="grid gap-6 xl:grid-cols-[1.45fr_0.95fr]">
                <div class="max-w-3xl">
                    <div class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-white/70">
                        Tenant Control Surface
                    </div>
                    <h1 class="mt-5 text-3xl font-semibold tracking-[-0.05em] text-white sm:text-[3.2rem]">
                        Provision with precision.
                    </h1>
                    <p class="mt-4 max-w-2xl text-sm leading-7 text-white/68 sm:text-[15px]">
                        One page to create a tenant, validate the host, carry the correct source, and immediately see whether the instance is truly live. No guesswork. No silent misses.
                    </p>

                    <div class="mt-6 grid gap-3 sm:grid-cols-3">
                        <div class="rounded-[1.35rem] border border-white/10 bg-white/6 px-4 py-4 backdrop-blur">
                            <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45">Active</div>
                            <div class="mt-2 text-3xl font-semibold tracking-tight text-white">{{ count($activeTenants) }}</div>
                            <div class="mt-1 text-xs text-white/55">Serving traffic now</div>
                        </div>
                        <div class="rounded-[1.35rem] border border-white/10 bg-white/6 px-4 py-4 backdrop-blur">
                            <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45">Disabled</div>
                            <div class="mt-2 text-3xl font-semibold tracking-tight text-white">{{ count($inactiveTenants) }}</div>
                            <div class="mt-1 text-xs text-white/55">Available for recovery</div>
                        </div>
                        <div class="rounded-[1.35rem] border border-white/10 bg-white/6 px-4 py-4 backdrop-blur">
                            <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45">Sources</div>
                            <div class="mt-2 text-3xl font-semibold tracking-tight text-white">{{ count($availableSources) }}</div>
                            <div class="mt-1 text-xs text-white/55">Clone points detected</div>
                        </div>
                    </div>
                </div>

                <div class="rounded-[1.75rem] border border-white/10 bg-white/6 p-5 backdrop-blur">
                    <div class="flex items-start justify-between gap-3">
                        <div>
                            <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-white/45">Deployment Contract</div>
                            <h2 class="mt-2 text-lg font-semibold tracking-tight text-white">What a complete run must leave behind</h2>
                        </div>
                        <x-filament::button wire:click="refreshData" size="sm" color="gray" class="!bg-white/10 !text-white hover:!bg-white/15">
                            Refresh
                        </x-filament::button>
                    </div>

                    <div class="mt-5 grid gap-3 sm:grid-cols-2">
                        @foreach ([
                            ['title' => 'DNS-ready host', 'copy' => 'Tenant host normalized to a bare domain before provisioning.'],
                            ['title' => 'Database clone', 'copy' => 'Fresh schema cloned and bound to the correct tenant database.'],
                            ['title' => 'TLS + nginx', 'copy' => 'Public route, certificate, and enabled nginx site available.'],
                            ['title' => 'Runtime ready', 'copy' => 'Laravel caches, storage link, scheduler, and worker configured.'],
                        ] as $item)
                            <div class="rounded-[1.2rem] border border-white/8 bg-black/15 p-4">
                                <div class="flex items-center gap-2 text-sm font-semibold text-white">
                                    <span class="inline-flex h-6 w-6 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300">✓</span>
                                    {{ $item['title'] }}
                                </div>
                                <p class="mt-2 text-xs leading-6 text-white/58">{{ $item['copy'] }}</p>
                            </div>
                        @endforeach
                    </div>
                </div>
            </div>
        </section>

        @if ($currentRunId)
            <section class="rounded-[1.6rem] border {{ $isRunning ? 'border-sky-500/20 bg-sky-500/8' : (($lastResult['success'] ?? false) ? 'border-emerald-500/20 bg-emerald-500/8' : 'border-rose-500/20 bg-rose-500/8') }} px-5 py-4 shadow-[0_20px_60px_-45px_rgba(15,23,42,0.8)]">
                <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div class="flex items-start gap-3">
                        <span class="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-2xl {{ $isRunning ? 'bg-sky-500/12 text-sky-300' : (($lastResult['success'] ?? false) ? 'bg-emerald-500/12 text-emerald-300' : 'bg-rose-500/12 text-rose-300') }}">
                            @if ($isRunning)
                                ↻
                            @elseif (($lastResult['success'] ?? false))
                                ✓
                            @else
                                !
                            @endif
                        </span>
                        <div>
                            <div class="text-[11px] font-semibold uppercase tracking-[0.2em] {{ $isRunning ? 'text-sky-300/80' : (($lastResult['success'] ?? false) ? 'text-emerald-300/80' : 'text-rose-300/80') }}">
                                {{ $isRunning ? 'Background Run Active' : 'Latest Provision Run' }}
                            </div>
                            <div class="mt-1 text-sm font-semibold text-white">
                                @if ($isRunning)
                                    Provisioning is continuing safely in the background.
                                @elseif (($lastResult['success'] ?? false))
                                    Provisioning completed successfully.
                                @else
                                    Provisioning finished with an error.
                                @endif
                            </div>
                            <p class="mt-1 text-xs leading-6 text-gray-400">
                                @if ($isRunning)
                                    You can stay on this page. It will refresh automatically until the run completes.
                                @elseif (($lastResult['success'] ?? false))
                                    The request returned already, and the page now reflects the final provisioning result.
                                @else
                                    The run finished server-side. Review the execution trace below instead of relying on the browser request state.
                                @endif
                            </p>
                        </div>
                    </div>

                    <div class="flex flex-wrap items-center gap-2">
                        <span class="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-300">
                            Run {{ \Illuminate\Support\Str::limit($currentRunId, 8, '') }}
                        </span>
                        <span class="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-300">
                            State {{ $runState }}
                        </span>
                    </div>
                </div>
            </section>
        @endif

        <div class="grid gap-6 xl:grid-cols-[1.4fr_0.95fr]">
            <div class="space-y-6">
                <section class="rounded-[2rem] border border-white/6 bg-white/[0.04] p-6 shadow-[0_24px_80px_-60px_rgba(15,23,42,0.85)] backdrop-blur sm:p-7">
                    <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                        <div class="max-w-2xl">
                            <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Provision New Tenant</div>
                            <h2 class="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">Make the outcome obvious before you deploy.</h2>
                            <p class="mt-3 text-sm leading-7 text-gray-400">
                                Enter the host, pick the right clone source, set operator credentials, and review the exact tenant that will be created.
                            </p>
                        </div>

                        <div class="grid min-w-[18rem] gap-3 sm:grid-cols-2 lg:grid-cols-1">
                            <div class="rounded-[1.35rem] border border-white/7 bg-black/20 p-4">
                                <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-gray-500">Preview URL</div>
                                <div class="mt-2 text-sm font-medium text-white break-all">
                                    {{ $preview['url'] !== '' ? $preview['url'] : 'https://your-tenant.sanaa.ug' }}
                                </div>
                            </div>
                            <div class="rounded-[1.35rem] border border-white/7 bg-black/20 p-4">
                                <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-gray-500">Resulting App / DB</div>
                                <div class="mt-2 text-sm font-medium text-white">
                                    {{ $preview['app_name'] !== '' ? $preview['app_name'] : 'auto-from-domain' }}
                                </div>
                                <div class="mt-1 text-xs text-gray-500">
                                    Database: {{ $preview['database'] !== '' ? $preview['database'] : 'pending' }}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="mt-6 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
                        <div class="space-y-5">
                            <div class="rounded-[1.5rem] border border-white/6 bg-black/15 p-5">
                                <div class="mb-4 flex items-center gap-3">
                                    <div class="inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-cyan-400/12 text-cyan-300">1</div>
                                    <div>
                                        <h3 class="text-sm font-semibold text-white">Identity</h3>
                                        <p class="text-xs text-gray-500">Define the tenant hostname and canonical app name.</p>
                                    </div>
                                </div>

                                <div class="grid gap-4">
                                    <div>
                                        <label class="mb-2 block text-sm font-medium text-gray-200">Domain</label>
                                        <input
                                            type="text"
                                            wire:model.live.debounce.300ms="domain"
                                            placeholder="kyaliwajjala.sanaa.ug or https://kyaliwajjala.sanaa.ug/"
                                            class="w-full rounded-[1rem] border border-white/10 bg-gray-950/80 px-4 py-3 text-sm text-white placeholder:text-gray-500 focus:border-cyan-400/50 focus:ring-cyan-400/30"
                                        />
                                        <div class="mt-2 flex flex-wrap gap-2 text-[11px] font-medium">
                                            <span class="rounded-full border px-3 py-1 {{ $preview['domain_valid'] ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-white/8 bg-white/5 text-gray-400' }}">
                                                {{ $preview['domain_valid'] ? 'Valid tenant host' : 'Expected format: name.sanaa.ug or name.sanaa.co' }}
                                            </span>
                                            @if ($preview['domain'] !== '' && $preview['domain'] !== $domain)
                                                <span class="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-cyan-300">
                                                    Normalized: {{ $preview['domain'] }}
                                                </span>
                                            @endif
                                        </div>
                                    </div>

                                    <div>
                                        <label class="mb-2 block text-sm font-medium text-gray-200">App Name</label>
                                        <input
                                            type="text"
                                            wire:model.live.debounce.300ms="appName"
                                            placeholder="Auto from domain"
                                            class="w-full rounded-[1rem] border border-white/10 bg-gray-950/80 px-4 py-3 text-sm text-white placeholder:text-gray-500 focus:border-cyan-400/50 focus:ring-cyan-400/30"
                                        />
                                        <p class="mt-2 text-xs text-gray-500">
                                            Leave blank to derive the app/database slug from the hostname automatically.
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <div class="rounded-[1.5rem] border border-white/6 bg-black/15 p-5">
                                <div class="mb-4 flex items-center gap-3">
                                    <div class="inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-indigo-400/12 text-indigo-300">2</div>
                                    <div>
                                        <h3 class="text-sm font-semibold text-white">Source & Access</h3>
                                        <p class="text-xs text-gray-500">Choose the canonical source and the admin credentials to stamp into the tenant.</p>
                                    </div>
                                </div>

                                <div class="grid gap-4 sm:grid-cols-2">
                                    <div class="sm:col-span-2">
                                        <label class="mb-2 block text-sm font-medium text-gray-200">Clone Source</label>
                                        <select
                                            wire:model.live="source"
                                            class="w-full rounded-[1rem] border border-white/10 bg-gray-950/80 px-4 py-3 text-sm text-white focus:border-indigo-400/50 focus:ring-indigo-400/30"
                                        >
                                            @foreach ($availableSources as $src)
                                                <option value="{{ $src['path'] }}">{{ $src['label'] }}</option>
                                            @endforeach
                                        </select>
                                        <div class="mt-3 grid gap-3 sm:grid-cols-3">
                                            <div class="rounded-[1rem] border border-white/7 bg-white/[0.03] p-3">
                                                <div class="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Source</div>
                                                <div class="mt-2 text-sm font-medium text-white">{{ $selectedSource['label'] ?? 'Template source' }}</div>
                                            </div>
                                            <div class="rounded-[1rem] border border-white/7 bg-white/[0.03] p-3">
                                                <div class="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Source DB</div>
                                                <div class="mt-2 text-sm font-medium text-white">{{ $preview['source_db'] }}</div>
                                            </div>
                                            <div class="rounded-[1rem] border border-white/7 bg-white/[0.03] p-3">
                                                <div class="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Path</div>
                                                <div class="mt-2 truncate text-sm font-medium text-white" title="{{ $preview['source_path'] }}">{{ $preview['source_path'] }}</div>
                                            </div>
                                        </div>
                                    </div>

                                    <div>
                                        <label class="mb-2 block text-sm font-medium text-gray-200">Admin Phone</label>
                                        <input
                                            type="text"
                                            wire:model="adminPhone"
                                            placeholder="+256..."
                                            class="w-full rounded-[1rem] border border-white/10 bg-gray-950/80 px-4 py-3 text-sm text-white placeholder:text-gray-500 focus:border-indigo-400/50 focus:ring-indigo-400/30"
                                        />
                                    </div>

                                    <div>
                                        <label class="mb-2 block text-sm font-medium text-gray-200">Admin Password</label>
                                        <input
                                            type="password"
                                            wire:model="adminPassword"
                                            placeholder="Set admin password"
                                            class="w-full rounded-[1rem] border border-white/10 bg-gray-950/80 px-4 py-3 text-sm text-white placeholder:text-gray-500 focus:border-indigo-400/50 focus:ring-indigo-400/30"
                                        />
                                    </div>
                                </div>
                            </div>

                            <div class="rounded-[1.5rem] border border-white/6 bg-black/15 p-5">
                                <div class="mb-4 flex items-center gap-3">
                                    <div class="inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-amber-400/12 text-amber-300">3</div>
                                    <div>
                                        <h3 class="text-sm font-semibold text-white">Safety & Finish</h3>
                                        <p class="text-xs text-gray-500">Choose whether to wipe operational data and whether the run should request TLS.</p>
                                    </div>
                                </div>

                                <div class="grid gap-3 sm:grid-cols-2">
                                    <label class="cursor-pointer rounded-[1rem] border {{ $wipeTenantData ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-white/8 bg-white/[0.03]' }} p-4 transition">
                                        <div class="flex items-start gap-3">
                                            <input type="checkbox" wire:model="wipeTenantData" class="mt-1 rounded border-white/15 bg-gray-950 text-emerald-500 focus:ring-emerald-500/40" />
                                            <div>
                                                <div class="text-sm font-semibold text-white">Clean slate</div>
                                                <p class="mt-1 text-xs leading-6 text-gray-400">Keep the configuration tables but wipe tenant operational data after cloning.</p>
                                            </div>
                                        </div>
                                    </label>

                                    <label class="cursor-pointer rounded-[1rem] border {{ $skipCert ? 'border-amber-500/30 bg-amber-500/10' : 'border-white/8 bg-white/[0.03]' }} p-4 transition">
                                        <div class="flex items-start gap-3">
                                            <input type="checkbox" wire:model="skipCert" class="mt-1 rounded border-white/15 bg-gray-950 text-amber-500 focus:ring-amber-500/40" />
                                            <div>
                                                <div class="text-sm font-semibold text-white">Skip TLS</div>
                                                <p class="mt-1 text-xs leading-6 text-gray-400">Testing only. Production tenants should finish with HTTPS and a public certificate.</p>
                                            </div>
                                        </div>
                                    </label>
                                </div>

                                <div class="mt-5 border-t border-white/6 pt-5">
                                    <div class="grid gap-4 rounded-[1.4rem] border border-emerald-500/18 bg-[linear-gradient(135deg,rgba(16,185,129,0.12),rgba(4,10,24,0.82))] p-4 shadow-[0_28px_80px_-52px_rgba(16,185,129,0.45)] lg:grid-cols-[1fr_auto] lg:items-center">
                                        <div>
                                            <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-300/80">Final Step</div>
                                            <div class="mt-2 text-base font-semibold text-white">
                                                Ready to create {{ $preview['domain'] !== '' ? $preview['domain'] : 'your next tenant' }}?
                                            </div>
                                            <p class="mt-2 max-w-2xl text-sm leading-6 text-gray-300">
                                                {{ $preview['clean_slate'] ? 'Operational data will be wiped after cloning.' : 'Source operational data will be retained.' }}
                                                {{ $preview['tls_mode'] === 'TLS enabled' ? ' HTTPS will be requested.' : ' TLS issuance will be skipped.' }}
                                            </p>
                                            <div class="mt-3 flex flex-wrap gap-2 text-[11px] font-medium">
                                                <span class="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-gray-300">
                                                    {{ $preview['url'] !== '' ? $preview['url'] : 'Tenant URL pending' }}
                                                </span>
                                                <span class="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-gray-300">
                                                    Source {{ $preview['source_label'] }}
                                                </span>
                                            </div>
                                        </div>

                                        <div class="flex flex-col items-stretch gap-3 lg:min-w-[20rem]">
                                            <x-filament::button
                                                wire:click="provisionTenant"
                                                color="success"
                                                size="lg"
                                                :disabled="$isRunning"
                                                class="!flex !w-full !items-center !justify-center !rounded-[1.2rem] !bg-emerald-500 !px-6 !py-4 !text-base !font-semibold !text-black !shadow-[0_26px_60px_-28px_rgba(16,185,129,0.9)] hover:!bg-emerald-400"
                                            >
                                                @if ($isRunning)
                                                    <span class="flex items-center gap-2">
                                                        <svg class="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                                                        </svg>
                                                        Provisioning in background...
                                                    </span>
                                                @else
                                                    <span class="flex items-center gap-2">
                                                        <span>Provision Tenant</span>
                                                        <span aria-hidden="true">→</span>
                                                    </span>
                                                @endif
                                            </x-filament::button>

                                            <div class="text-center text-xs font-medium {{ $isRunning ? 'text-sky-300' : 'text-gray-400' }}">
                                                {{ $isRunning ? 'The request has already returned. This page is polling for the final result.' : 'This is the action that creates the tenant.' }}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <aside class="space-y-5">
                            <div class="rounded-[1.5rem] border border-white/6 bg-black/15 p-5">
                                <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-500">Live Preview</div>
                                <h3 class="mt-2 text-lg font-semibold tracking-tight text-white">Provision intent</h3>

                                <div class="mt-4 space-y-3">
                                    @foreach ([
                                        ['label' => 'Host', 'value' => $preview['domain'] !== '' ? $preview['domain'] : 'Not set'],
                                        ['label' => 'App slug', 'value' => $preview['app_name'] !== '' ? $preview['app_name'] : 'Auto from host'],
                                        ['label' => 'Database', 'value' => $preview['database'] !== '' ? $preview['database'] : 'Pending'],
                                        ['label' => 'TLS', 'value' => $preview['tls_mode']],
                                        ['label' => 'Source', 'value' => $preview['source_label']],
                                    ] as $item)
                                        <div class="flex items-start justify-between gap-4 rounded-[1rem] border border-white/7 bg-white/[0.03] px-4 py-3">
                                            <span class="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">{{ $item['label'] }}</span>
                                            <span class="max-w-[70%] break-all text-right text-sm font-medium text-white">{{ $item['value'] }}</span>
                                        </div>
                                    @endforeach
                                </div>
                            </div>

                            <div class="rounded-[1.5rem] border border-white/6 bg-black/15 p-5">
                                <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-500">Operator Checklist</div>
                                <div class="mt-4 space-y-3">
                                    @foreach ([
                                        'Use the bare tenant host. Full URLs will be normalized automatically.',
                                        'Confirm the clone source before deploying. Most tenants should start from finance.',
                                        'Set an admin password during provisioning so the handoff is clean.',
                                        'Run a health check immediately after provisioning if you changed DNS or source.',
                                    ] as $rule)
                                        <div class="flex gap-3 rounded-[1rem] border border-white/7 bg-white/[0.03] px-4 py-3">
                                            <span class="mt-0.5 text-cyan-300">•</span>
                                            <p class="text-sm leading-6 text-gray-300">{{ $rule }}</p>
                                        </div>
                                    @endforeach
                                </div>
                            </div>
                        </aside>
                    </div>
                </section>

                @if ($provisionLog || $statusOutput)
                    <section class="grid gap-6 xl:grid-cols-2">
                        @if ($provisionLog)
                            <x-filament::card class="!rounded-[1.75rem] !border-white/6 !bg-white/[0.03] !shadow-none">
                                <div class="mb-3 flex items-center justify-between gap-3">
                                    <div>
                                        <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-500">Execution Trace</div>
                                        <h3 class="mt-1 text-lg font-semibold tracking-tight text-white">Provisioning Log</h3>
                                    </div>

                                    @if ($isRunning)
                                        <span class="rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-300">In Progress</span>
                                    @elseif ($lastResult && ($lastResult['success'] ?? false))
                                        <span class="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-300">Success</span>
                                    @elseif ($lastResult)
                                        <span class="rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-300">Failed</span>
                                    @endif
                                </div>

                                <pre class="max-h-[34rem] overflow-auto rounded-[1.2rem] border border-white/8 bg-gray-950/95 p-4 text-xs leading-relaxed text-emerald-200 whitespace-pre-wrap font-mono">{{ $provisionLog }}</pre>
                            </x-filament::card>
                        @endif

                        @if ($statusOutput)
                            <x-filament::card class="!rounded-[1.75rem] !border-white/6 !bg-white/[0.03] !shadow-none">
                                <div class="mb-3">
                                    <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-500">Verification</div>
                                    <h3 class="mt-1 text-lg font-semibold tracking-tight text-white">Health Check</h3>
                                </div>

                                <pre class="max-h-[34rem] overflow-auto rounded-[1.2rem] border border-white/8 bg-gray-950/95 p-4 text-xs leading-relaxed text-sky-200 whitespace-pre-wrap font-mono">{{ $statusOutput }}</pre>
                            </x-filament::card>
                        @endif
                    </section>
                @endif
            </div>

            <aside class="space-y-6">
                <section class="rounded-[2rem] border border-white/6 bg-white/[0.04] p-6 shadow-[0_24px_80px_-60px_rgba(15,23,42,0.85)] backdrop-blur">
                    <div class="flex items-start justify-between gap-3">
                        <div>
                            <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-500">Tenant Estate</div>
                            <h2 class="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">Live fleet</h2>
                            <p class="mt-2 text-sm leading-7 text-gray-400">
                                The tenants that exist right now, with fast access to health and state changes.
                            </p>
                        </div>

                        <div class="rounded-[1.1rem] border border-white/7 bg-black/20 px-4 py-3 text-right">
                            <div class="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Total</div>
                            <div class="mt-1 text-2xl font-semibold tracking-tight text-white">{{ $this->getTenantCount() }}</div>
                        </div>
                    </div>

                    <div class="mt-5 rounded-[1.5rem] border border-white/7 bg-black/15 p-4">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <div class="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Default Template</div>
                                <div class="mt-1 text-sm font-semibold text-white">{{ $selectedSource['label'] ?? 'finance (template)' }}</div>
                            </div>
                            <div class="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-300">
                                {{ $dbSource }}
                            </div>
                        </div>
                    </div>

                    <div class="mt-5 space-y-5">
                        <div>
                            <div class="mb-3 flex items-center justify-between">
                                <h3 class="text-sm font-semibold text-white">Active</h3>
                                <span class="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-300">
                                    {{ count($activeTenants) }}
                                </span>
                            </div>

                            <div class="space-y-3">
                                @forelse ($activeTenants as $tenant)
                                    <div class="rounded-[1.3rem] border border-white/7 bg-black/15 p-4">
                                        <div class="flex items-start justify-between gap-3">
                                            <div>
                                                <a href="https://{{ $tenant['domain'] }}" target="_blank" class="text-sm font-semibold text-cyan-300 transition hover:text-cyan-200 hover:underline">
                                                    {{ $tenant['domain'] }}
                                                </a>
                                                <div class="mt-1 text-xs text-gray-500">
                                                    {{ $tenant['db_tables'] ?? '?' }} tables
                                                </div>
                                            </div>
                                            <span class="mt-1 inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_18px_rgba(74,222,128,0.65)]"></span>
                                        </div>

                                        <div class="mt-4 flex flex-wrap gap-2">
                                            <button
                                                wire:click="checkStatus('{{ $tenant['domain'] }}')"
                                                class="rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300 transition hover:bg-sky-500/15"
                                            >
                                                Health Check
                                            </button>
                                            <button
                                                wire:click="disableTenant('{{ $tenant['domain'] }}')"
                                                wire:confirm="Disable {{ $tenant['domain'] }}? The site will go offline."
                                                class="rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/15"
                                            >
                                                Disable
                                            </button>
                                        </div>
                                    </div>
                                @empty
                                    <div class="rounded-[1.3rem] border border-dashed border-white/10 bg-black/15 px-4 py-8 text-center text-sm text-gray-500">
                                        No active tenants yet.
                                    </div>
                                @endforelse
                            </div>
                        </div>

                        @if (count($inactiveTenants) > 0)
                            <div class="border-t border-white/6 pt-5">
                                <div class="mb-3 flex items-center justify-between">
                                    <h3 class="text-sm font-semibold text-white">Disabled</h3>
                                    <span class="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">
                                        {{ count($inactiveTenants) }}
                                    </span>
                                </div>

                                <div class="space-y-3">
                                    @foreach ($inactiveTenants as $tenant)
                                        <div class="rounded-[1.3rem] border border-white/7 bg-black/15 p-4 opacity-80">
                                            <div class="flex items-start justify-between gap-3">
                                                <div>
                                                    <div class="text-sm font-medium text-gray-300">{{ $tenant['domain'] }}</div>
                                                    <div class="mt-1 text-xs text-gray-500">{{ $tenant['db_tables'] ?? '?' }} tables</div>
                                                </div>
                                                <span class="mt-1 inline-flex h-2.5 w-2.5 rounded-full bg-gray-500"></span>
                                            </div>

                                            <div class="mt-4 flex flex-wrap gap-2">
                                                <button
                                                    wire:click="enableTenant('{{ $tenant['domain'] }}')"
                                                    class="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-300 transition hover:bg-emerald-500/15"
                                                >
                                                    Re-enable
                                                </button>
                                                <button
                                                    wire:click="checkStatus('{{ $tenant['domain'] }}')"
                                                    class="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-gray-300 transition hover:bg-white/[0.08]"
                                                >
                                                    Check
                                                </button>
                                            </div>
                                        </div>
                                    @endforeach
                                </div>
                            </div>
                        @endif
                    </div>
                </section>
            </aside>
        </div>
    </div>
</x-filament-panels::page>
