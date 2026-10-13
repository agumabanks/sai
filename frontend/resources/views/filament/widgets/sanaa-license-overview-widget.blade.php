<x-filament-widgets::widget>
    <div class="relative overflow-hidden rounded-2xl bg-white/[0.04] backdrop-blur-[40px] p-6 lg:p-7 border border-white/[0.08] shadow-[0_4px_24px_rgba(0,0,0,0.25)]">

        {{-- Ambient glow orb --}}
        <div class="pointer-events-none absolute -top-10 -right-10 h-40 w-40 rounded-full opacity-20"
             style="background: radial-gradient(circle, hsla(234,89%,64%,0.6) 0%, transparent 70%);"></div>

        <div class="relative z-10 space-y-6">

            {{-- Header --}}
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="h-9 w-9 rounded-xl flex items-center justify-center"
                         style="background: rgba(94,92,230,0.15); border: 1px solid rgba(94,92,230,0.25);">
                        <x-heroicon-m-key class="h-4 w-4 text-indigo-400" />
                    </div>
                    <div>
                        <p class="text-[10px] font-bold tracking-[0.12em] uppercase text-white/40">License Command</p>
                        <p class="text-base font-semibold text-white/90 leading-tight">Sanaa License Overview</p>
                    </div>
                </div>

                <x-filament::button
                    wire:click="refreshData"
                    size="sm"
                    color="gray"
                    outlined
                    icon="heroicon-m-arrow-path"
                    class="text-white/60"
                >
                    Refresh
                </x-filament::button>
            </div>

            {{-- Metric Cards --}}
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <x-metric-card
                    label="Total Tenants"
                    :value="$totalTenants"
                    icon="heroicon-m-users"
                    color="primary"
                />
                <x-metric-card
                    label="Active"
                    :value="$activeTenants"
                    icon="heroicon-m-check-badge"
                    color="success"
                />
                <x-metric-card
                    label="Expiring This Week"
                    :value="$expiringThisWeek"
                    icon="heroicon-m-clock"
                    color="warning"
                />
                <x-metric-card
                    label="Suspended"
                    :value="$suspendedTenants"
                    icon="heroicon-m-no-symbol"
                    color="danger"
                />
            </div>

            {{-- Expiring Tenants List --}}
            <div class="rounded-xl bg-white/[0.02] border border-white/[0.06] p-4">
                <div class="flex items-center justify-between mb-3">
                    <h4 class="text-[12px] font-semibold text-white/70 uppercase tracking-wide">Tenants Expiring in Next 7 Days</h4>
                    <span class="text-[11px] text-white/40">{{ count($expiringTenants) }} shown</span>
                </div>

                @if(count($expiringTenants) > 0)
                    <div class="overflow-x-auto">
                        <table class="w-full text-left">
                            <thead>
                                <tr class="border-b border-white/[0.06]">
                                    <th class="py-2 pr-4 text-[10px] font-semibold text-white/40 uppercase tracking-wide">Tenant</th>
                                    <th class="py-2 pr-4 text-[10px] font-semibold text-white/40 uppercase tracking-wide">Plan</th>
                                    <th class="py-2 pr-4 text-[10px] font-semibold text-white/40 uppercase tracking-wide">Status</th>
                                    <th class="py-2 pr-4 text-[10px] font-semibold text-white/40 uppercase tracking-wide">Expires</th>
                                    <th class="py-2 pr-4 text-[10px] font-semibold text-white/40 uppercase tracking-wide">Days Left</th>
                                    <th class="py-2 text-right text-[10px] font-semibold text-white/40 uppercase tracking-wide">Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                @foreach($expiringTenants as $tenant)
                                    <tr class="border-b border-white/[0.03] last:border-0 hover:bg-white/[0.02] transition-colors">
                                        <td class="py-3 pr-4 text-[12px] font-medium text-white/80">{{ $tenant['tenant_name'] }}</td>
                                        <td class="py-3 pr-4 text-[12px] text-white/60">{{ $tenant['plan_name'] }}</td>
                                        <td class="py-3 pr-4">
                                            <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium"
                                                  style="background: {{ match($tenant['status_color']) {
                                                      'success' => 'rgba(48,209,88,0.12)',
                                                      'info' => 'rgba(10,132,255,0.12)',
                                                      'warning' => 'rgba(255,159,10,0.12)',
                                                      'danger' => 'rgba(255,69,58,0.12)',
                                                      default => 'rgba(120,120,128,0.12)',
                                                  } }}; color: {{ match($tenant['status_color']) {
                                                      'success' => '#30d158',
                                                      'info' => '#0a84ff',
                                                      'warning' => '#ff9f0a',
                                                      'danger' => '#ff453a',
                                                      default => '#8e8e93',
                                                  } }}; border: 1px solid {{ match($tenant['status_color']) {
                                                      'success' => 'rgba(48,209,88,0.2)',
                                                      'info' => 'rgba(10,132,255,0.2)',
                                                      'warning' => 'rgba(255,159,10,0.2)',
                                                      'danger' => 'rgba(255,69,58,0.2)',
                                                      default => 'rgba(120,120,128,0.2)',
                                                  } }}">
                                                {{ ucfirst($tenant['status']) }}
                                            </span>
                                        </td>
                                        <td class="py-3 pr-4 text-[12px] text-white/60">
                                            {{ $tenant['subscription_ends_at'] ? \Carbon\Carbon::parse($tenant['subscription_ends_at'])->format('M d, Y') : '—' }}
                                        </td>
                                        <td class="py-3 pr-4 text-[12px] font-medium {{ $tenant['days_left'] < 0 ? 'text-[#ff453a]' : ($tenant['days_left'] <= 3 ? 'text-[#ff9f0a]' : 'text-[#30d158]') }}">
                                            {{ $tenant['days_left'] }}
                                        </td>
                                        <td class="py-3 text-right">
                                            <x-filament::button
                                                wire:click="quickRecordPayment('{{ $tenant['id'] }}')"
                                                size="xs"
                                                color="success"
                                                icon="heroicon-m-banknotes"
                                            >
                                                Record Payment
                                            </x-filament::button>
                                        </td>
                                    </tr>
                                @endforeach
                            </tbody>
                        </table>
                    </div>
                @else
                    <div class="flex flex-col items-center justify-center py-8">
                        <div class="w-12 h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-4">
                            <x-heroicon-m-shield-check class="w-6 h-6 text-[#30d158] opacity-80" />
                        </div>
                        <p class="text-[13px] font-medium text-white/70 mb-1">No expiring tenants</p>
                        <p class="text-[11px] text-white/35">All licenses are healthy</p>
                    </div>
                @endif
            </div>

        </div>
    </div>
</x-filament-widgets::widget>
