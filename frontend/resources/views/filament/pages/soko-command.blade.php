<x-filament-panels::page>
    {{-- Header --}}
    <x-filament::card>
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-lg font-semibold">Soko 24 — Command Center</h2>
                <div class="text-sm text-gray-500">
                    Soko Monitoring Agent active. Connected to soko24 DB.
                </div>
            </div>
            <x-filament::button wire:click="refreshAll" size="sm" color="gray">Refresh Data</x-filament::button>
        </div>
    </x-filament::card>

    {{-- KPI Cards --}}
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Total Users</div>
            <div class="text-2xl font-bold mt-1">{{ number_format($health['total_users'] ?? 0) }}</div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Active Sellers</div>
            <div class="text-2xl font-bold mt-1">{{ number_format($health['active_sellers'] ?? 0) }}</div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Total Products</div>
            <div class="text-2xl font-bold mt-1">{{ number_format($health['active_products'] ?? 0) }}</div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">24H Revenue (Paid)</div>
            <div class="text-2xl font-bold mt-1 text-green-600">
                UGX {{ number_format($metrics['daily_revenue'] ?? 0, 0) }}
            </div>
        </x-filament::card>
    </div>

    <div class="grid gap-6 lg:grid-cols-3 mt-6">
        {{-- ========== Left: Main Panel ========== --}}
        <div class="lg:col-span-2 space-y-4">
            
            @if(count($distressed) > 0)
                <x-filament::card>
                    <h3 class="text-base font-semibold mb-3 text-red-600">🚨 Distressed Sellers (> 48h Delayed Orders)</h3>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm whitespace-nowrap">
                            <thead>
                                <tr class="text-gray-500 border-b border-gray-200 dark:border-gray-700">
                                    <th class="py-2">Shop Name</th>
                                    <th class="py-2">Phone</th>
                                    <th class="py-2">Pending Orders</th>
                                </tr>
                            </thead>
                            <tbody>
                                @foreach($distressed as $seller)
                                <tr class="border-b border-gray-100 dark:border-gray-800">
                                    <td class="py-2 font-medium">{{ $seller['shop_name'] }}</td>
                                    <td class="py-2">{{ $seller['phone'] }}</td>
                                    <td class="py-2 text-amber-500 font-bold">{{ $seller['pending_orders'] }}</td>
                                </tr>
                                @endforeach
                            </tbody>
                        </table>
                    </div>
                </x-filament::card>
            @endif

            <x-filament::card>
                <h3 class="text-base font-semibold mb-3">Order Pipeline Health (Last 7 Days)</h3>
                @if(isset($metrics['recent_orders']) && count($metrics['recent_orders']) > 0)
                    <ul class="space-y-2 text-sm">
                        @foreach($metrics['recent_orders'] as $row)
                            <li class="flex justify-between border-b pb-1">
                                <span>
                                    <span class="font-medium text-gray-700 dark:text-gray-300">Payment:</span> {{ $row['payment_status'] ?: 'N/A' }} 
                                    <span class="font-medium text-gray-700 dark:text-gray-300 ml-4">Delivery:</span> {{ $row['delivery_status'] ?: 'N/A' }}
                                </span>
                                <span class="font-bold">{{ $row['count'] }}</span>
                            </li>
                        @endforeach
                    </ul>
                @else
                    <p class="text-gray-500 text-sm">No recent orders found.</p>
                @endif
            </x-filament::card>
        </div>

        {{-- ========== Right: Operations Panel ========== --}}
        <div class="space-y-4">
            <x-filament::card>
                <h3 class="text-base font-semibold mb-3">Agent Actions</h3>
                <div class="space-y-2">
                    <button wire:click="runCheck('platform_health')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'platform_health' ? 'bg-primary-50 text-primary-700' : 'bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700' }} transition">
                        Check Platform Health
                    </button>
                    <button wire:click="runCheck('order_metrics')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'order_metrics' ? 'bg-green-50 text-green-700' : 'bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700' }} transition">
                        Check Order Metrics
                    </button>
                    <button wire:click="runCheck('distressed_sellers')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'distressed_sellers' ? 'bg-red-50 text-red-700' : 'bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700' }} transition">
                        Scan Distressed Sellers
                    </button>
                </div>
            </x-filament::card>

            @if ($detailOutput)
                <x-filament::card>
                    <h3 class="text-sm font-semibold mb-2 capitalize">{{ str_replace('_', ' ', $activeTab) }} Output</h3>
                    <pre class="text-xs overflow-auto max-h-[30rem] bg-gray-950 text-green-200 p-4 rounded whitespace-pre-wrap font-mono leading-relaxed">{{ $detailOutput }}</pre>
                </x-filament::card>
            @endif
        </div>
    </div>
</x-filament-panels::page>
