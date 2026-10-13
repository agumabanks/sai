<x-filament-panels::page>
    <style>
        .briefing-settings-shell {
            display: grid;
            gap: 1.5rem;
        }

        .briefing-panel {
            border-radius: 18px;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background:
                radial-gradient(circle at top right, rgba(45, 212, 191, 0.14), transparent 26%),
                linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(2, 6, 23, 0.98));
            box-shadow: 0 24px 70px rgba(2, 6, 23, 0.18);
            color: #e5e7eb;
        }

        .briefing-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.38rem 0.85rem;
            border-radius: 9999px;
            border: 1px solid rgba(45, 212, 191, 0.22);
            background: rgba(45, 212, 191, 0.08);
            color: #99f6e4;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
        }

        .briefing-stat-grid {
            display: grid;
            gap: 1rem;
        }

        .briefing-stat {
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.14);
            background: rgba(15, 23, 42, 0.56);
            padding: 1rem 1.15rem;
        }

        .briefing-stat h4 {
            margin: 0;
            color: #94a3b8;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
        }

        .briefing-stat p {
            margin: 0.6rem 0 0;
            color: #f8fafc;
            font-size: 1.8rem;
            font-weight: 800;
            line-height: 1;
        }

        .briefing-card {
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.12);
            background: rgba(15, 23, 42, 0.56);
            padding: 1.2rem;
        }

        .briefing-delivery-row {
            display: grid;
            gap: 0.75rem;
        }

        .briefing-delivery-item {
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.14);
            background: rgba(2, 6, 23, 0.34);
            padding: 0.85rem;
        }

        .briefing-delivery-item span {
            display: block;
            color: #64748b;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }

        .briefing-delivery-item p {
            margin-top: 0.45rem;
            color: #e5e7eb;
            font-size: 0.82rem;
            line-height: 1.45;
            word-break: break-word;
        }

        .briefing-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 9999px;
            padding: 0.3rem 0.72rem;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }

        .briefing-chip.info {
            background: rgba(59, 130, 246, 0.12);
            border: 1px solid rgba(59, 130, 246, 0.2);
            color: #93c5fd;
        }

        .briefing-chip.success {
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #86efac;
        }

        .briefing-chip.warn {
            background: rgba(245, 158, 11, 0.12);
            border: 1px solid rgba(245, 158, 11, 0.22);
            color: #fcd34d;
        }

        @media (min-width: 1024px) {
            .briefing-settings-shell {
                grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
            }

            .briefing-stat-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }

            .briefing-delivery-row {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }

        @media (max-width: 640px) {
            .briefing-panel {
                padding: 1.25rem !important;
            }

            .briefing-panel h1 {
                font-size: 1.65rem;
                line-height: 1.15;
            }
        }
    </style>

    <div class="briefing-settings-shell">
        <div class="space-y-6">
            <div class="briefing-panel p-8">
                <div class="briefing-kicker">Sanaa Media Intelligence</div>
                <h1 class="mt-4 text-3xl font-black tracking-tight text-white">Executive Daily Briefing Control</h1>
                <p class="mt-3 max-w-3xl text-sm leading-7 text-slate-300">
                    Control automatic delivery, monitor briefing quality, and trigger the newsroom pipeline whenever you need a fresh executive edition.
                </p>

                <div class="briefing-stat-grid mt-6">
                    <div class="briefing-stat">
                        <h4>Latest Briefing</h4>
                        <p>{{ $latestBriefing ? \Illuminate\Support\Carbon::parse($latestBriefing['created_at'])->format('d M') : '--' }}</p>
                    </div>
                    <div class="briefing-stat">
                        <h4>Signal Score</h4>
                        <p>{{ $latestSignal['score'] ?? '--' }}</p>
                    </div>
                    <div class="briefing-stat">
                        <h4>QA Score</h4>
                        <p>{{ $briefingQa['score'] ?? '--' }}</p>
                    </div>
                </div>

                <div class="briefing-delivery-row mt-5">
                    <div class="briefing-delivery-item">
                        <span>Email</span>
                        <p>{{ filled($data['email_recipients'] ?? '') ? $data['email_recipients'] : 'No Sanaa Media email recipients saved yet.' }}</p>
                    </div>
                    <div class="briefing-delivery-item">
                        <span>PDF</span>
                        <p>{{ ($data['pdf_attachment'] ?? true) ? 'Enabled for email attachments and archive download.' : 'Disabled for new editions.' }}</p>
                    </div>
                    <div class="briefing-delivery-item">
                        <span>WhatsApp</span>
                        <p>{{ ($data['whatsapp_delivery'] ?? true) ? (filled($data['whatsapp_recipients'] ?? '') ? $data['whatsapp_recipients'] : 'Enabled, but no recipient is saved.') : 'Disabled for news delivery.' }}</p>
                    </div>
                </div>
            </div>

            <div class="briefing-card">
                <div class="mb-5 flex items-center justify-between gap-4">
                    <div>
                        <h2 class="text-lg font-bold text-white">Delivery Preferences</h2>
                        <p class="mt-1 text-sm text-slate-400">Configure when the daily intelligence briefing should be generated and dispatched.</p>
                    </div>
                    <button wire:click="refreshOverview" class="rounded-2xl border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800">
                        Refresh Status
                    </button>
                </div>

                <form wire:submit="submit">
                    {{ $this->form }}

                    <div class="mt-6 flex flex-col gap-3 sm:flex-row">
                        <x-filament::button type="submit">
                            Save Preferences
                        </x-filament::button>
                        <x-filament::button type="button" color="gray" wire:click="loadPreferences" icon="heroicon-m-arrow-path">
                            Reload Saved Values
                        </x-filament::button>
                    </div>
                </form>
            </div>
        </div>

        <div class="space-y-6">
            <div class="briefing-card">
                <div class="flex items-start justify-between gap-4">
                    <div>
                        <h2 class="text-lg font-bold text-white">Manual Generation</h2>
                        <p class="mt-2 text-sm leading-7 text-slate-400">
                            Trigger the newsroom pipeline now to aggregate feeds, synthesize the executive briefing, build the PDF, and dispatch the email edition.
                        </p>
                    </div>
                    <span class="briefing-chip warn">On Demand</span>
                </div>

                <div class="mt-5">
                    <x-filament::button wire:click="generateNow" color="warning" icon="heroicon-m-bolt">
                        Generate Briefing Now
                    </x-filament::button>
                </div>
            </div>

            <div class="briefing-card">
                <div class="flex items-center justify-between gap-3">
                    <h2 class="text-lg font-bold text-white">Latest Briefing</h2>
                    @if($latestBriefing)
                        <span class="briefing-chip success">{{ $latestBriefing['metadata']['article_count'] ?? 0 }} stories</span>
                    @endif
                </div>

                @if($latestBriefing)
                    <div class="mt-4 space-y-3">
                        <div class="text-sm font-semibold text-white">{{ $latestBriefing['title'] }}</div>
                        <div class="text-xs text-slate-500">
                            {{ \Illuminate\Support\Carbon::parse($latestBriefing['created_at'])->diffForHumans() }}
                        </div>
                        <div class="flex flex-wrap gap-2">
                            @foreach(array_slice($latestBriefing['metadata']['topics'] ?? [], 0, 5) as $topic)
                                <span class="briefing-chip info">{{ $topic }}</span>
                            @endforeach
                        </div>
                        <div class="flex flex-wrap gap-2 pt-2">
                            @if($this->getLatestBriefingPdfUrl())
                                <a href="{{ $this->getLatestBriefingPdfUrl() }}" target="_blank" class="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs font-bold text-emerald-100 transition hover:bg-emerald-400/16">
                                    Open PDF
                                </a>
                            @else
                                <span class="briefing-chip warn">PDF pending</span>
                            @endif
                            <a href="{{ route('filament.admin.pages.intelligence-archive') }}" class="rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs font-bold text-slate-200 transition hover:bg-slate-800">
                                View Archive
                            </a>
                        </div>
                    </div>
                @else
                    <p class="mt-4 text-sm text-slate-500">No archived briefing found yet.</p>
                @endif
            </div>

            <div class="briefing-card">
                <div class="flex items-center justify-between gap-3">
                    <h2 class="text-lg font-bold text-white">Quality & Signal Status</h2>
                    @if($latestSignal)
                        <span class="briefing-chip info">Score {{ $latestSignal['score'] }}</span>
                    @endif
                </div>

                <div class="mt-4 space-y-4">
                    <div>
                        <div class="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500">Top Signal</div>
                        <div class="mt-2 text-sm leading-7 text-slate-200">
                            {{ $latestSignal['title'] ?? 'No strategic signal available yet.' }}
                        </div>
                    </div>

                    <div>
                        <div class="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500">Latest QA</div>
                        @if($briefingQa)
                            <div class="mt-2 text-sm leading-7 text-slate-200">
                                {{ $briefingQa['summary'] ?? $briefingQa['analysis'] ?? 'QA data is available, but no summary text was returned.' }}
                            </div>
                        @else
                            <div class="mt-2 text-sm leading-7 text-slate-500">
                                No recent briefing QA assessment available yet.
                            </div>
                        @endif
                    </div>
                </div>
            </div>
        </div>
    </div>
</x-filament-panels::page>
