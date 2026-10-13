<x-filament-widgets::widget class="h-full">
    <style>
        .intelligence-widget-shell {
            border-radius: 28px;
            border: 1px solid rgba(148, 163, 184, 0.14);
            background:
                radial-gradient(circle at top right, rgba(45, 212, 191, 0.14), transparent 28%),
                linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(2, 6, 23, 0.98));
            box-shadow: 0 22px 60px rgba(2, 6, 23, 0.18);
            color: #e5e7eb;
        }

        .intelligence-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.28rem 0.7rem;
            border-radius: 9999px;
            border: 1px solid rgba(45, 212, 191, 0.22);
            background: rgba(45, 212, 191, 0.08);
            color: #99f6e4;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.2em;
            text-transform: uppercase;
        }

        .intelligence-card {
            border-radius: 22px;
            border: 1px solid rgba(148, 163, 184, 0.12);
            background: rgba(15, 23, 42, 0.62);
            padding: 1rem;
        }

        .intelligence-mini-stat {
            border-radius: 18px;
            border: 1px solid rgba(148, 163, 184, 0.12);
            background: rgba(15, 23, 42, 0.54);
            padding: 0.85rem 0.95rem;
            text-align: center;
        }
    </style>

    <div class="intelligence-widget-shell h-full p-6">
        <div class="space-y-5">
            <div class="flex items-start justify-between gap-4">
                <div>
                    <div class="intelligence-chip">Sanaa Media Intelligence</div>
                    <h3 class="mt-3 text-lg font-bold tracking-tight text-white">Executive Daily Briefing</h3>
                    <p class="mt-2 text-sm leading-6 text-slate-400">
                        Strategic signals, briefing recaps, and PDF-ready intelligence at a glance.
                    </p>
                </div>
                <a
                    href="{{ route('filament.admin.pages.intelligence-archive') }}"
                    class="inline-flex items-center gap-1 rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-800"
                >
                    Open
                    <x-heroicon-m-arrow-right class="h-3.5 w-3.5" />
                </a>
            </div>

            @if($warningMessage)
                <div class="rounded-[22px] border border-amber-400/25 bg-amber-400/10 px-4 py-3">
                    <div class="flex items-start gap-3">
                        <div class="mt-0.5 flex h-8 w-8 items-center justify-center rounded-2xl bg-amber-300/12 text-amber-200">
                            <x-heroicon-m-exclamation-triangle class="h-4 w-4" />
                        </div>
                        <div class="min-w-0">
                            <p class="text-xs font-bold uppercase tracking-[0.22em] text-amber-200">Engine Attention Required</p>
                            <p class="mt-2 text-sm leading-6 text-amber-50">{{ $warningMessage }}</p>
                        </div>
                    </div>
                </div>
            @endif

            @if($latestSignal)
                <div class="intelligence-card">
                    <div class="flex items-start gap-3">
                        <div class="flex h-10 w-10 items-center justify-center rounded-2xl bg-amber-400/12 text-amber-300">
                            <x-heroicon-m-signal class="h-5 w-5" />
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="flex flex-wrap items-center gap-2">
                                <span class="text-[10px] font-bold uppercase tracking-[0.22em] text-amber-300">Top Signal</span>
                                <span class="rounded-full border border-amber-400/20 bg-amber-400/10 px-2 py-0.5 text-[10px] font-bold text-amber-200">
                                    Score {{ $latestSignal['score'] }}/10
                                </span>
                            </div>
                            <p class="mt-2 text-sm font-semibold leading-6 text-white">{{ $latestSignal['title'] }}</p>
                            <p class="mt-2 text-xs text-slate-500">{{ $latestSignal['time']->diffForHumans() }}</p>
                        </div>
                    </div>
                </div>
            @endif

            @if($latestBriefing)
                <a href="{{ route('filament.admin.pages.intelligence-archive') }}" class="intelligence-card block transition hover:border-cyan-400/24 hover:bg-slate-900/88">
                    <div class="flex items-start justify-between gap-4">
                        <div class="min-w-0">
                            <div class="text-[10px] font-bold uppercase tracking-[0.22em] text-slate-500">Latest Briefing</div>
                            <h4 class="mt-2 text-base font-bold leading-7 text-white">{{ $latestBriefing['title'] }}</h4>
                        </div>
                        <div class="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-200">
                            Open
                        </div>
                    </div>

                    <div class="mt-4 flex flex-wrap gap-2">
                        <span class="rounded-full border border-slate-700 bg-slate-900/70 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-300">
                            {{ $latestBriefing['articleCount'] }} stories
                        </span>
                        @foreach(array_slice($latestBriefing['topics'] ?? [], 0, 3) as $topic)
                            <span class="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-200">
                                {{ $topic }}
                            </span>
                        @endforeach
                    </div>

                    <p class="mt-3 text-xs text-slate-500">{{ $latestBriefing['time']->diffForHumans() }}</p>
                </a>
            @endif

            <div class="grid grid-cols-2 gap-3">
                <div class="intelligence-mini-stat">
                    <div class="text-2xl font-black text-white">{{ $briefingCount }}</div>
                    <div class="mt-1 text-[10px] font-bold uppercase tracking-[0.22em] text-slate-500">Recent Briefings</div>
                </div>
                <div class="intelligence-mini-stat">
                    <div class="text-2xl font-black text-amber-300">{{ $latestSignal['score'] ?? '-' }}</div>
                    <div class="mt-1 text-[10px] font-bold uppercase tracking-[0.22em] text-slate-500">Signal Score</div>
                </div>
            </div>

            @if(!$latestBriefing && !$latestSignal)
                <div class="rounded-[24px] border border-dashed border-slate-700 px-6 py-10 text-center">
                    <x-heroicon-m-newspaper class="mx-auto mb-3 h-8 w-8 text-slate-600" />
                    <p class="text-sm font-semibold text-slate-300">{{ $warningMessage ? 'Intelligence feed unavailable' : 'No intelligence yet' }}</p>
                    <p class="mt-1 text-xs text-slate-500">
                        {{ $warningMessage ? 'Check the Sanaa Engine backend service, SANAA_ENGINE_URL, and the Nginx /api proxy target before retrying.' : 'Generate a briefing from the control center to populate this panel.' }}
                    </p>
                </div>
            @endif
        </div>
    </div>
</x-filament-widgets::widget>
