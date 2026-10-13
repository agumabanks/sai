<div class="space-y-3 p-1">
    @forelse($events as $event)
        @php
            $eventColor = match($event->event_type) {
                'checked' => '#0a84ff',
                'warned' => '#ff9f0a',
                'suspended', 'killed' => '#ff453a',
                'reactivated' => '#30d158',
                'payment_recorded' => '#30d158',
                'plan_changed' => '#bf5af2',
                default => '#8e8e93',
            };
        @endphp
        <div class="flex items-start gap-3 py-2.5 px-3 rounded-xl bg-white/[0.02] border border-white/[0.04]">
            <div class="w-2 h-2 rounded-full mt-1.5 shrink-0" style="background: {{ $eventColor }}; box-shadow: 0 0 8px {{ $eventColor }}60;"></div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between">
                    <p class="text-[12px] font-medium text-white/80">{{ ucfirst(str_replace('_', ' ', $event->event_type)) }}</p>
                    <span class="text-[10px] text-white/40">{{ $event->created_at->diffForHumans() }}</span>
                </div>
                <p class="text-[11px] text-white/50 mt-0.5">Triggered by: {{ ucfirst($event->triggered_by) }}</p>
                @if(!empty($event->payload))
                    <div class="mt-2 text-[10px] text-white/40 font-mono bg-white/[0.03] rounded-lg p-2 overflow-x-auto">
                        <pre>{{ json_encode($event->payload, JSON_PRETTY_PRINT) }}</pre>
                    </div>
                @endif
            </div>
        </div>
    @empty
        <div class="flex flex-col items-center justify-center py-10">
            <div class="w-12 h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-4">
                <x-heroicon-m-inbox class="w-6 h-6 text-white/40" />
            </div>
            <p class="text-[13px] font-medium text-white/70 mb-1">No events found</p>
            <p class="text-[11px] text-white/35">This tenant has no recorded activity yet.</p>
        </div>
    @endforelse
</div>
