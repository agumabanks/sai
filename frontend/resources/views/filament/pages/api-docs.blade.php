<x-filament-panels::page class="relative">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#5e5ce6]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#0a84ff]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-40"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#5e5ce6] to-[#0a84ff] flex items-center justify-center shadow-lg shadow-[#5e5ce6]/20">
                    @svg('heroicon-o-document-text', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">API Documentation</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">{{ $this->getApiInfo()['title'] ?? 'Sanaa AI Engine' }} — OpenAPI Specification</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                @php
                    $apiInfo = $this->getApiInfo();
                    $endpointCount = $this->getEndpointCount();
                @endphp
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#30d158]"></span>
                    v{{ $apiInfo['version'] ?? '?.?.?' }}
                </div>
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#5e5ce6]"></span>
                    {{ $endpointCount }} endpoints
                </div>
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    OpenAPI {{ $this->getOpenApiVersion() }}
                </div>
                <button wire:click="refreshSpec"
                        class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#5e5ce6]/20 border border-[#5e5ce6]/30 text-[#5e5ce6] text-[11px] font-medium uppercase tracking-wide hover:bg-[#5e5ce6]/30 transition-colors cursor-pointer">
                    @svg('heroicon-o-arrow-path', 'w-3.5 h-3.5')
                    Refresh
                </button>
            </div>
        </div>

        {{-- ── API Info Card ───────────────────────────────────────────────── --}}
        @if(!empty($apiInfo['description']))
            <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md p-5">
                <p class="text-sm text-white/60">{{ $apiInfo['description'] }}</p>
            </div>
        @endif

        {{-- ── Security Schemes ────────────────────────────────────────────── --}}
        @php $securitySchemes = $this->getSecuritySchemes(); @endphp
        @if(!empty($securitySchemes))
            <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md p-5">
                <h3 class="text-xs font-semibold text-white/40 uppercase tracking-wider mb-3">Authentication</h3>
                <div class="flex flex-wrap gap-2">
                    @foreach($securitySchemes as $name => $scheme)
                        <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#ff9f0a]/10 border border-[#ff9f0a]/20 text-[11px] font-medium text-[#ff9f0a]">
                            @svg('heroicon-o-lock-closed', 'w-3.5 h-3.5')
                            {{ $name }}: {{ $scheme['scheme'] ?? $scheme['type'] ?? 'unknown' }}
                        </div>
                    @endforeach
                </div>
            </div>
        @endif

        {{-- ── Endpoints ───────────────────────────────────────────────────── --}}
        @php $paths = $this->getPaths(); @endphp
        @if(!empty($paths))
            <div class="space-y-3">
                <h2 class="text-xs font-semibold text-white/40 uppercase tracking-wider">Endpoints</h2>

                @foreach($paths as $path => $methods)
                    @foreach($methods as $method => $detail)
                        @php
                            $isExpanded = $this->isExpanded($path, $method);
                            $methodUpper = strtoupper($method);
                            $badgeClasses = $this->getMethodBadge($method);
                        @endphp

                        <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md overflow-hidden transition-all duration-200">
                            {{-- Endpoint Header --}}
                            <button wire:click="toggleEndpoint('{{ $path }}', '{{ $method }}')"
                                    class="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-white/[0.02] transition-colors cursor-pointer text-left">
                                {{-- Method Badge --}}
                                <span class="inline-flex items-center px-2.5 py-1 rounded-md border text-[10px] font-bold tracking-wider {{ $badgeClasses }}">
                                    {{ $methodUpper }}
                                </span>

                                {{-- Path --}}
                                <span class="font-mono text-sm text-white/80 flex-1 truncate">{{ $path }}</span>

                                {{-- Summary --}}
                                @if(!empty($detail['summary']))
                                    <span class="text-xs text-white/35 hidden sm:inline truncate max-w-[300px]">{{ $detail['summary'] }}</span>
                                @endif

                                {{-- Expand indicator --}}
                                <span class="text-white/20 transition-transform duration-200 {{ $isExpanded ? 'rotate-180' : '' }}">
                                    @svg('heroicon-o-chevron-down', 'w-4 h-4')
                                </span>
                            </button>

                            {{-- Endpoint Detail (expanded) --}}
                            @if($isExpanded)
                                <div class="border-t border-white/[0.06] px-5 py-4 space-y-4">
                                    {{-- Description --}}
                                    @if(!empty($detail['description']))
                                        <div>
                                            <h4 class="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-1">Description</h4>
                                            <p class="text-sm text-white/60">{{ $detail['description'] }}</p>
                                        </div>
                                    @endif

                                    {{-- Tags --}}
                                    @if(!empty($detail['tags']))
                                        <div>
                                            <h4 class="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-1">Tags</h4>
                                            <div class="flex flex-wrap gap-1.5">
                                                @foreach($detail['tags'] as $tag)
                                                    <span class="px-2 py-0.5 rounded-md bg-[#5e5ce6]/10 border border-[#5e5ce6]/20 text-[10px] text-[#5e5ce6] font-medium">
                                                        {{ $tag }}
                                                    </span>
                                                @endforeach
                                            </div>
                                        </div>
                                    @endif

                                    {{-- Parameters --}}
                                    @if(!empty($detail['parameters']))
                                        <div>
                                            <h4 class="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-2">Parameters</h4>
                                            <div class="rounded-xl bg-black/30 border border-white/[0.04] overflow-hidden">
                                                <table class="w-full text-xs">
                                                    <thead>
                                                        <tr class="border-b border-white/[0.06]">
                                                            <th class="text-left px-3 py-2 text-white/30 font-medium">Name</th>
                                                            <th class="text-left px-3 py-2 text-white/30 font-medium">In</th>
                                                            <th class="text-left px-3 py-2 text-white/30 font-medium">Type</th>
                                                            <th class="text-left px-3 py-2 text-white/30 font-medium">Required</th>
                                                            <th class="text-left px-3 py-2 text-white/30 font-medium">Description</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        @foreach($detail['parameters'] as $param)
                                                            <tr class="border-b border-white/[0.03]">
                                                                <td class="px-3 py-2 font-mono text-white/70">{{ $param['name'] ?? '—' }}</td>
                                                                <td class="px-3 py-2 text-white/40">{{ $param['in'] ?? '—' }}</td>
                                                                <td class="px-3 py-2 text-[#0a84ff]">{{ $param['schema']['type'] ?? '—' }}</td>
                                                                <td class="px-3 py-2">
                                                                    @if($param['required'] ?? false)
                                                                        <span class="text-[#ff453a]">yes</span>
                                                                    @else
                                                                        <span class="text-white/25">no</span>
                                                                    @endif
                                                                </td>
                                                                <td class="px-3 py-2 text-white/40">{{ $param['description'] ?? '' }}</td>
                                                            </tr>
                                                        @endforeach
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    @endif

                                    {{-- Request Body --}}
                                    @if(!empty($detail['requestBody']))
                                        <div>
                                            <h4 class="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-2">Request Body</h4>
                                            @foreach(($detail['requestBody']['content'] ?? []) as $contentType => $content)
                                                <div class="rounded-xl bg-black/30 border border-white/[0.04] p-3">
                                                    <div class="text-[10px] text-white/30 mb-2 font-mono">{{ $contentType }}</div>
                                                    @if(!empty($content['schema']))
                                                        <pre class="text-xs text-white/50 font-mono whitespace-pre-wrap overflow-x-auto max-h-48">{{ $this->formatSchema($content['schema']) }}</pre>
                                                    @endif
                                                </div>
                                            @endforeach
                                        </div>
                                    @endif

                                    {{-- Responses --}}
                                    @if(!empty($detail['responses']))
                                        <div>
                                            <h4 class="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-2">Responses</h4>
                                            <div class="space-y-2">
                                                @foreach($detail['responses'] as $statusCode => $response)
                                                    @php
                                                        $codeColor = match(true) {
                                                            str_starts_with((string)$statusCode, '2') => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                                                            str_starts_with((string)$statusCode, '3') => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20',
                                                            str_starts_with((string)$statusCode, '4') => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                                                            str_starts_with((string)$statusCode, '5') => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                                                            default => 'text-white/40 bg-white/5 border-white/10',
                                                        };
                                                    @endphp
                                                    <div class="flex items-start gap-3 rounded-xl bg-black/20 border border-white/[0.04] px-3 py-2">
                                                        <span class="inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-bold {{ $codeColor }}">
                                                            {{ $statusCode }}
                                                        </span>
                                                        <span class="text-xs text-white/40">{{ $response['description'] ?? '' }}</span>
                                                    </div>
                                                @endforeach
                                            </div>
                                        </div>
                                    @endif
                                </div>
                            @endif
                        </div>
                    @endforeach
                @endforeach
            </div>
        @else
            {{-- Empty State --}}
            <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md p-12 text-center">
                @svg('heroicon-o-document-text', 'w-12 h-12 text-white/20 mx-auto mb-4')
                <h3 class="text-sm font-medium text-white/60 mb-1">No API Specification Available</h3>
                <p class="text-xs text-white/30">Could not load the OpenAPI spec from the backend. Ensure the API is running.</p>
                <button wire:click="refreshSpec"
                        class="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#5e5ce6]/20 border border-[#5e5ce6]/30 text-[#5e5ce6] text-xs font-medium hover:bg-[#5e5ce6]/30 transition-colors cursor-pointer">
                    @svg('heroicon-o-arrow-path', 'w-4 h-4')
                    Retry
                </button>
            </div>
        @endif
    </div>
</x-filament-panels::page>
