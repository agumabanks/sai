<x-filament-panels::page>
    <x-filament::card>
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-lg font-semibold">System Doctor</h2>
                <div class="text-sm text-gray-500">Safety and configuration audit checks (OpenClaw-style).</div>
            </div>
            <x-filament::button wire:click="refreshData">Run Checks</x-filament::button>
        </div>

        <div class="mt-4">
            <div class="text-sm">
                Status:
                <span class="font-semibold">{{ strtoupper($report['status'] ?? 'UNKNOWN') }}</span>
            </div>
            <div class="text-xs text-gray-500 mt-1">
                OK: {{ $report['summary']['ok'] ?? 0 }},
                Warn: {{ $report['summary']['warn'] ?? 0 }},
                Fail: {{ $report['summary']['fail'] ?? 0 }}
            </div>
        </div>

        <div class="mt-4 overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b">
                        <th class="text-left py-2">Check</th>
                        <th class="text-left py-2">Severity</th>
                        <th class="text-left py-2">Result</th>
                        <th class="text-left py-2">Message</th>
                    </tr>
                </thead>
                <tbody>
                    @forelse (($report['checks'] ?? []) as $check)
                        <tr class="border-b align-top">
                            <td class="py-2 text-xs">{{ $check['id'] ?? '-' }}</td>
                            <td class="py-2">{{ strtoupper($check['severity'] ?? '-') }}</td>
                            <td class="py-2">
                                @if (!empty($check['ok']))
                                    <span class="text-green-600">OK</span>
                                @else
                                    <span class="text-red-600">FAIL</span>
                                @endif
                            </td>
                            <td class="py-2">{{ $check['message'] ?? '' }}</td>
                        </tr>
                    @empty
                        <tr><td colspan="4" class="py-4 text-gray-500">No doctor data available.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </x-filament::card>

    <div class="grid gap-6 lg:grid-cols-2 mt-6">
        <x-filament::card>
            <h2 class="text-lg font-semibold">Watchdog Advisor</h2>
            <pre class="mt-4 text-xs overflow-auto max-h-[24rem] bg-gray-950 text-green-200 p-4 rounded">{{ json_encode($watchdogAdvisor, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) }}</pre>
        </x-filament::card>
        <x-filament::card>
            <h2 class="text-lg font-semibold">Latest Briefing QA</h2>
            <pre class="mt-4 text-xs overflow-auto max-h-[24rem] bg-gray-950 text-green-200 p-4 rounded">{{ json_encode($briefingQa, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) }}</pre>
        </x-filament::card>
    </div>
</x-filament-panels::page>

