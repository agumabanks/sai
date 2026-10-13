<x-filament-panels::page>
    @php
        $briefingMeta = $this->getSelectedBriefingMetadata();
        $topSignals = $this->getSelectedTopSignals();
        $topics = $this->getSelectedBriefingTopics();
        $sections = $this->getSelectedSections();
        $pdfUrl = $this->getSelectedPdfUrl();
        $pdfFilename = $this->getSelectedPdfFilename();
    @endphp

    <style>
        .media-shell {
            display: grid;
            gap: 1.5rem;
        }

        .media-panel {
            border-radius: 18px;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(2, 6, 23, 0.98));
            box-shadow: 0 24px 70px rgba(2, 6, 23, 0.22);
            color: #e5e7eb;
        }

        .media-panel-soft {
            background:
                radial-gradient(circle at top right, rgba(45, 212, 191, 0.16), transparent 28%),
                linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(2, 6, 23, 0.98));
        }

        .media-kicker {
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
            letter-spacing: 0.24em;
            text-transform: uppercase;
        }

        .media-stat-grid {
            display: grid;
            gap: 1rem;
        }

        .media-stat-card {
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(15, 23, 42, 0.72);
            padding: 1rem 1.15rem;
        }

        .media-stat-card h4 {
            margin: 0;
            color: #94a3b8;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.24em;
            text-transform: uppercase;
        }

        .media-stat-card p {
            margin: 0.55rem 0 0;
            color: #f8fafc;
            font-size: 1.75rem;
            font-weight: 800;
            line-height: 1;
        }

        .media-feed-item {
            width: 100%;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.14);
            background: rgba(15, 23, 42, 0.54);
            padding: 1rem 1.05rem;
            text-align: left;
            color: #e5e7eb;
            transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
        }

        .media-feed-item:hover {
            transform: translateY(-2px);
            border-color: rgba(99, 102, 241, 0.3);
            background: rgba(30, 41, 59, 0.78);
        }

        .media-feed-item.is-active {
            border-color: rgba(99, 102, 241, 0.5);
            background: linear-gradient(180deg, rgba(49, 46, 129, 0.22), rgba(15, 23, 42, 0.86));
            box-shadow: 0 18px 38px rgba(37, 99, 235, 0.12);
        }

        .media-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 9999px;
            padding: 0.3rem 0.7rem;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }

        .media-pill.info {
            background: rgba(59, 130, 246, 0.12);
            border: 1px solid rgba(59, 130, 246, 0.22);
            color: #93c5fd;
        }

        .media-pill.success {
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.22);
            color: #86efac;
        }

        .media-pill.warn {
            background: rgba(245, 158, 11, 0.12);
            border: 1px solid rgba(245, 158, 11, 0.22);
            color: #fcd34d;
        }

        .media-signal-card {
            border-radius: 14px;
            border: 1px solid rgba(45, 212, 191, 0.16);
            background: rgba(15, 23, 42, 0.62);
            padding: 1rem;
            color: #e5e7eb;
        }

        .media-prose {
            color: #dbe4f0;
            line-height: 1.88;
        }

        .media-prose h2 {
            color: #f8fafc;
            font-size: 1.4rem;
            font-weight: 800;
            margin-top: 2.4rem;
            margin-bottom: 1rem;
            letter-spacing: -0.02em;
        }

        .media-prose h3 {
            color: #c4b5fd;
            font-size: 1rem;
            font-weight: 800;
            margin-top: 1.7rem;
            margin-bottom: 0.9rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .media-prose p,
        .media-prose li {
            font-size: 0.98rem;
        }

        .media-prose strong {
            color: #ffffff;
        }

        .media-prose ul {
            margin: 1rem 0;
            padding-left: 1.2rem;
        }

        .media-empty {
            min-height: 640px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
        }

        @media (min-width: 768px) {
            .media-shell {
                grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
            }

            .media-stat-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }

            .media-signals-grid {
                display: grid;
                gap: 1rem;
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }

        @media (max-width: 767px) {
            .media-panel {
                border-radius: 14px;
            }

            .media-empty {
                min-height: 360px;
            }
        }
    </style>

    <div class="media-shell">
        <aside class="space-y-6">
            <div class="media-panel media-panel-soft p-6">
                <div class="media-kicker">Sanaa Media Intelligence</div>
                <h1 class="mt-4 text-3xl font-black tracking-tight text-white">Executive Daily Briefing</h1>
                <p class="mt-3 text-sm leading-7 text-slate-300">
                    A curated archive of strategic signals, market narratives, and East Africa-focused business context prepared for executive reading.
                </p>

                <div class="media-stat-grid mt-6">
                    <div class="media-stat-card">
                        <h4>Briefings</h4>
                        <p>{{ count($briefings) }}</p>
                    </div>
                    <div class="media-stat-card">
                        <h4>Latest Signal</h4>
                        <p>{{ $latestSignal['score'] ?? '-' }}</p>
                    </div>
                    <div class="media-stat-card">
                        <h4>Topics</h4>
                        <p>{{ count($topics) }}</p>
                    </div>
                </div>
            </div>

            <div class="media-panel p-5">
                <div class="mb-4 flex items-center justify-between">
                    <h2 class="text-sm font-bold uppercase tracking-[0.28em] text-slate-400">Briefing Archive</h2>
                    <div class="media-pill info">Live Feed</div>
                </div>

                <div class="space-y-3">
                    @forelse($briefings as $b)
                        @php
                            $isActive = ($selectedBriefing['id'] ?? null) === $b['id'];
                            $articleCount = $b['metadata']['article_count'] ?? 0;
                            $topicCount = count($b['metadata']['topics'] ?? []);
                        @endphp
                        <button
                            type="button"
                            wire:click="selectBriefing({{ $b['id'] }})"
                            class="media-feed-item {{ $isActive ? 'is-active' : '' }}"
                        >
                            <div class="flex items-start justify-between gap-3">
                                <div class="min-w-0">
                                    <div class="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500">
                                        {{ now()->parse($b['created_at'])->format('d M · H:i') }}
                                    </div>
                                    <div class="mt-2 text-sm font-bold leading-6 text-white">
                                        {{ $b['title'] }}
                                    </div>
                                </div>
                                @if($b['pdf_path'] ?? false)
                                    <div class="media-pill success">PDF</div>
                                @endif
                            </div>

                            <div class="mt-4 flex flex-wrap gap-2">
                                <span class="media-pill info">{{ $articleCount }} stories</span>
                                <span class="media-pill warn">{{ $topicCount }} topics</span>
                            </div>
                        </button>
                    @empty
                        <div class="rounded-[24px] border border-dashed border-slate-700 px-6 py-16 text-center">
                            <x-heroicon-o-inbox class="mx-auto mb-4 h-10 w-10 text-slate-600" />
                            <div class="text-sm font-bold uppercase tracking-[0.24em] text-slate-500">No Briefings Yet</div>
                        </div>
                    @endforelse
                </div>
            </div>
        </aside>

        <section>
            @if($selectedBriefing)
                <div class="media-panel media-panel-soft p-8 md:p-10">
                    <div class="flex flex-col gap-8">
                        <div class="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                            <div class="max-w-4xl">
                                <div class="flex flex-wrap items-center gap-3">
                                    <span class="media-pill success">Executive Briefing</span>
                                    <span class="text-xs font-bold uppercase tracking-[0.22em] text-slate-500">
                                        {{ now()->parse($selectedBriefing['created_at'])->format('l, d M Y') }}
                                    </span>
                                </div>
                                <h2 class="mt-4 text-2xl font-black tracking-tight text-white md:text-4xl">
                                    {{ $selectedBriefing['title'] }}
                                </h2>
                                <p class="mt-4 max-w-3xl text-sm leading-7 text-slate-300">
                                    Prepared by Sanaa Media Intelligence for executive review. The briefing below combines strategic signals, sector narratives, and actionable opportunity context.
                                </p>
                            </div>

                            <div class="flex flex-wrap gap-3">
                                @if($pdfUrl)
                                    <a
                                        href="{{ $pdfUrl }}"
                                        target="_blank"
                                        class="inline-flex items-center gap-2 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-5 py-3 text-sm font-bold text-emerald-100 transition hover:bg-emerald-400/16"
                                    >
                                        <x-heroicon-o-arrow-down-tray class="h-5 w-5" />
                                        Download PDF
                                    </a>
                                @else
                                    <span class="inline-flex items-center gap-2 rounded-2xl border border-slate-700 bg-slate-900/60 px-5 py-3 text-sm font-bold text-slate-400">
                                        <x-heroicon-o-document class="h-5 w-5" />
                                        PDF Pending
                                    </span>
                                @endif
                                <button wire:click="refreshData" class="inline-flex items-center gap-2 rounded-2xl border border-slate-600 bg-slate-900/70 px-5 py-3 text-sm font-bold text-white transition hover:bg-slate-800">
                                    <x-heroicon-o-arrow-path class="h-5 w-5" />
                                    Refresh
                                </button>
                            </div>
                        </div>

                        <div class="media-stat-grid">
                            <div class="media-stat-card">
                                <h4>Stories Reviewed</h4>
                                <p>{{ $briefingMeta['article_count'] ?? 0 }}</p>
                            </div>
                            <div class="media-stat-card">
                                <h4>Signal Cards</h4>
                                <p>{{ count($topSignals) }}</p>
                            </div>
                            <div class="media-stat-card">
                                <h4>Sector Sections</h4>
                                <p>{{ count($sections) }}</p>
                            </div>
                        </div>

                        @if(count($topics))
                            <div class="flex flex-wrap gap-2">
                                @foreach(array_slice($topics, 0, 8) as $topic)
                                    <span class="media-pill info">{{ $topic }}</span>
                                @endforeach
                            </div>
                        @endif

                        @if(count($topSignals))
                            <div>
                                <div class="mb-4 text-sm font-bold uppercase tracking-[0.28em] text-slate-400">Top Strategic Signals</div>
                                <div class="media-signals-grid gap-4">
                                    @foreach(array_slice($topSignals, 0, 3) as $signal)
                                        <div class="media-signal-card">
                                            <div class="text-[11px] font-bold uppercase tracking-[0.22em] text-teal-300">Signal {{ $loop->iteration }}</div>
                                            <div class="mt-3 text-base font-semibold leading-7 text-white">{{ $signal }}</div>
                                        </div>
                                    @endforeach
                                </div>
                            </div>
                        @endif

                        <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr),300px]">
                            <div class="rounded-2xl border border-slate-700/70 bg-slate-950/65 p-5 md:p-7">
                                <div class="media-prose prose prose-invert max-w-none">
                                    {!! str($selectedBriefing['content'])->markdown() !!}
                                </div>
                            </div>

                            <div class="space-y-5">
                                <div class="rounded-2xl border border-slate-700/70 bg-slate-950/65 p-5">
                                    <div class="text-sm font-bold uppercase tracking-[0.26em] text-slate-400">Briefing Map</div>
                                    <div class="mt-4 space-y-2">
                                        @forelse($sections as $section)
                                            <div class="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm font-semibold text-slate-200">
                                                {{ $section }}
                                            </div>
                                        @empty
                                            <div class="text-sm text-slate-500">Section structure will appear here once headings are present.</div>
                                        @endforelse
                                    </div>
                                </div>

                                <div class="rounded-2xl border border-slate-700/70 bg-slate-950/65 p-5">
                                    <div class="text-sm font-bold uppercase tracking-[0.26em] text-slate-400">Distribution</div>
                                    <div class="mt-4 space-y-3">
                                        <div class="media-pill {{ $pdfUrl ? 'success' : 'warn' }}">{{ $pdfUrl ? 'PDF ready' : 'PDF pending' }}</div>
                                        <div class="text-sm leading-7 text-slate-300">
                                            {{ $pdfUrl ? ($pdfFilename ?: 'Executive PDF is available for email and WhatsApp sharing.') : 'No PDF file was found for this briefing yet.' }}
                                        </div>
                                        @if($pdfUrl)
                                            <a href="{{ $pdfUrl }}" target="_blank" class="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-2.5 text-xs font-bold text-emerald-100 transition hover:bg-emerald-400/16">
                                                <x-heroicon-o-eye class="h-4 w-4" />
                                                Open PDF
                                            </a>
                                        @endif
                                    </div>
                                </div>

                                <div class="rounded-2xl border border-slate-700/70 bg-slate-950/65 p-5">
                                    <div class="text-sm font-bold uppercase tracking-[0.26em] text-slate-400">WhatsApp Share</div>
                                    <div class="mt-4 space-y-3">
                                        <input
                                            type="text"
                                            wire:model.defer="whatsAppPhone"
                                            placeholder="2567..."
                                            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
                                        />
                                        <button
                                            type="button"
                                            wire:click="shareSelectedBriefingToWhatsApp"
                                            wire:loading.attr="disabled"
                                            class="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-blue-400/25 bg-blue-500/15 px-4 py-3 text-sm font-bold text-blue-100 transition hover:bg-blue-500/22 disabled:cursor-not-allowed disabled:opacity-60"
                                        >
                                            <x-heroicon-o-paper-airplane class="h-4 w-4" />
                                            <span wire:loading.remove wire:target="shareSelectedBriefingToWhatsApp">Send Briefing</span>
                                            <span wire:loading wire:target="shareSelectedBriefingToWhatsApp">Sending...</span>
                                        </button>
                                        <p class="text-xs leading-5 text-slate-500">
                                            Sends the executive digest and attaches the PDF when the file is available.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            @else
                <div class="media-panel media-empty p-10">
                    <div class="media-kicker">Archive Ready</div>
                    <h3 class="mt-6 text-3xl font-black tracking-tight text-white">Select a briefing to begin</h3>
                    <p class="mt-3 max-w-xl text-sm leading-7 text-slate-400">
                        Choose a daily briefing from the archive to review signals, sector coverage, topics, and the executive PDF version.
                    </p>
                </div>
            @endif
        </section>
    </div>
</x-filament-panels::page>
