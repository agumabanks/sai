<x-filament-panels::page>
    <div class="space-y-8">
        {{-- Status Header --}}
        <div class="glass-dark rounded-[32px] p-8 shadow-2xl overflow-hidden relative animate-fade-in">
            <div class="absolute -top-32 -right-32 w-64 h-64 bg-emerald-500/6 blur-[100px] rounded-full"></div>
            <div class="absolute -bottom-32 -left-32 w-64 h-64 bg-sanaa-indigo/5 blur-[100px] rounded-full"></div>

            <div class="relative z-10">
                {{-- Header --}}
                <div class="flex items-center justify-between border-b border-white/5 pb-6 mb-8">
                    <div class="flex items-center gap-4">
                        <div class="w-14 h-14 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                            <svg class="w-7 h-7" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                            </svg>
                        </div>
                        <div>
                            <h2 class="text-lg font-black text-white tracking-tight">WhatsApp Command Center</h2>
                            <p class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.12em] mt-0.5">WhatsJet Cloud API Integration</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-3">
                        <button wire:click="refreshStatus" class="p-2.5 rounded-xl glass hover:glass-light transition-all group">
                            <x-heroicon-m-arrow-path class="w-4 h-4 text-gray-400 group-hover:text-white transition" />
                        </button>
                        <a href="{{ config('services.whatsapp.admin_url', 'https://wa.sanaa.co') }}" target="_blank"
                           class="flex items-center gap-2 px-4 py-2.5 rounded-xl glass hover:glass-light border border-white/5 hover:border-sanaa-indigo/30 transition-all text-xs font-bold text-gray-300 hover:text-white">
                            <x-heroicon-m-arrow-top-right-on-square class="w-4 h-4" />
                            WhatsJet Admin
                        </a>
                    </div>
                </div>

                {{-- Status Cards Grid --}}
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {{-- Connection Status --}}
                    <div class="p-5 rounded-2xl glass border border-white/5">
                        <div class="flex items-center gap-3 mb-3">
                            <div class="w-10 h-10 rounded-xl {{ ($status['healthy'] ?? false) ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500' }} flex items-center justify-center">
                                @if($status['healthy'] ?? false)
                                    <x-heroicon-m-signal class="w-5 h-5" />
                                @else
                                    <x-heroicon-m-signal-slash class="w-5 h-5" />
                                @endif
                            </div>
                            <div>
                                <p class="text-[9px] font-bold text-gray-500 uppercase tracking-widest">Status</p>
                                <p class="text-sm font-black {{ ($status['healthy'] ?? false) ? 'text-emerald-400' : 'text-red-400' }}">
                                    {{ ($status['healthy'] ?? false) ? 'Connected' : 'Offline' }}
                                </p>
                            </div>
                        </div>
                    </div>

                    {{-- Service Running --}}
                    <div class="p-5 rounded-2xl glass border border-white/5">
                        <div class="flex items-center gap-3 mb-3">
                            <div class="w-10 h-10 rounded-xl {{ ($status['running'] ?? false) ? 'bg-sanaa-indigo/10 text-sanaa-indigo' : 'bg-gray-500/10 text-gray-500' }} flex items-center justify-center">
                                <x-heroicon-m-server class="w-5 h-5" />
                            </div>
                            <div>
                                <p class="text-[9px] font-bold text-gray-500 uppercase tracking-widest">Service</p>
                                <p class="text-sm font-black {{ ($status['running'] ?? false) ? 'text-white' : 'text-gray-500' }}">
                                    {{ ($status['running'] ?? false) ? 'Running' : 'Stopped' }}
                                </p>
                            </div>
                        </div>
                    </div>

                    {{-- Vendor Config --}}
                    <div class="p-5 rounded-2xl glass border border-white/5">
                        <div class="flex items-center gap-3 mb-3">
                            <div class="w-10 h-10 rounded-xl {{ !empty($status['vendor_uid'] ?? '') ? 'bg-sanaa-cyan/10 text-sanaa-cyan' : 'bg-amber-500/10 text-amber-500' }} flex items-center justify-center">
                                <x-heroicon-m-key class="w-5 h-5" />
                            </div>
                            <div>
                                <p class="text-[9px] font-bold text-gray-500 uppercase tracking-widest">Vendor</p>
                                <p class="text-sm font-black {{ !empty($status['vendor_uid'] ?? '') ? 'text-white' : 'text-amber-400' }}">
                                    {{ !empty($status['vendor_uid'] ?? '') ? 'Configured' : 'Not Set' }}
                                </p>
                            </div>
                        </div>
                    </div>

                    {{-- API Token --}}
                    <div class="p-5 rounded-2xl glass border border-white/5">
                        <div class="flex items-center gap-3 mb-3">
                            <div class="w-10 h-10 rounded-xl {{ ($status['has_api_token'] ?? false) ? 'bg-purple-500/10 text-purple-500' : 'bg-amber-500/10 text-amber-500' }} flex items-center justify-center">
                                <x-heroicon-m-shield-check class="w-5 h-5" />
                            </div>
                            <div>
                                <p class="text-[9px] font-bold text-gray-500 uppercase tracking-widest">API Token</p>
                                <p class="text-sm font-black {{ ($status['has_api_token'] ?? false) ? 'text-white' : 'text-amber-400' }}">
                                    {{ ($status['has_api_token'] ?? false) ? 'Active' : 'Not Set' }}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        {{-- Actions & Quick Send --}}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            {{-- Quick Send --}}
            <div class="glass-dark rounded-[32px] p-8 shadow-2xl overflow-hidden relative">
                <div class="absolute -top-24 -left-24 w-48 h-48 bg-emerald-500/5 blur-[80px] rounded-full"></div>
                <div class="relative z-10 space-y-6">
                    <div class="flex items-center gap-3 border-b border-white/5 pb-5">
                        <div class="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                            <x-heroicon-m-paper-airplane class="w-5 h-5" />
                        </div>
                        <div>
                            <h3 class="text-[15px] font-black text-white">Quick Send</h3>
                            <p class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.12em]">Send Test Message</p>
                        </div>
                    </div>

                    <div class="space-y-4">
                        <div>
                            <label class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.12em] mb-2 block">Phone Number</label>
                            <input type="text" wire:model="sendPhone" placeholder="256700123456"
                                   class="w-full px-4 py-3 rounded-xl glass border border-white/5 focus:border-emerald-500/30 bg-transparent text-white text-sm font-medium placeholder-gray-600 outline-none transition" />
                        </div>
                        <div>
                            <label class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.12em] mb-2 block">Message</label>
                            <textarea wire:model="sendMessage" placeholder="Type your message..."
                                      rows="3"
                                      class="w-full px-4 py-3 rounded-xl glass border border-white/5 focus:border-emerald-500/30 bg-transparent text-white text-sm font-medium placeholder-gray-600 outline-none transition resize-none"></textarea>
                        </div>
                        <button wire:click="sendTestMessage"
                                class="w-full flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-black uppercase tracking-widest transition-all shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30">
                            <x-heroicon-m-paper-airplane class="w-4 h-4" />
                            Send Message
                        </button>
                    </div>
                </div>
            </div>

            {{-- Quick Actions --}}
            <div class="glass-dark rounded-[32px] p-8 shadow-2xl overflow-hidden relative">
                <div class="absolute -top-24 -right-24 w-48 h-48 bg-sanaa-indigo/5 blur-[80px] rounded-full"></div>
                <div class="relative z-10 space-y-6">
                    <div class="flex items-center gap-3 border-b border-white/5 pb-5">
                        <div class="w-10 h-10 rounded-xl bg-sanaa-indigo/10 flex items-center justify-center text-sanaa-indigo">
                            <x-heroicon-m-squares-2x2 class="w-5 h-5" />
                        </div>
                        <div>
                            <h3 class="text-[15px] font-black text-white">Quick Actions</h3>
                            <p class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.12em]">Management Shortcuts</p>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <a href="{{ config('services.whatsapp.admin_url', 'https://wa.sanaa.co') }}" target="_blank"
                           class="group p-5 rounded-2xl glass hover:glass-light border border-white/5 hover:border-emerald-500/30 transition-all duration-300 hover:-translate-y-1">
                            <div class="flex flex-col items-center gap-3">
                                <div class="w-12 h-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-500 group-hover:bg-emerald-500 group-hover:text-white transition-all shadow-lg shadow-emerald-500/5 group-hover:shadow-emerald-500/30">
                                    <x-heroicon-m-chat-bubble-left-right class="w-6 h-6" />
                                </div>
                                <div class="text-center">
                                    <span class="text-xs font-bold text-white">Chatbox</span>
                                    <p class="text-[8px] text-gray-500 font-medium uppercase tracking-wider mt-1">Live Chat</p>
                                </div>
                            </div>
                        </a>

                        <a href="{{ config('services.whatsapp.admin_url', 'https://wa.sanaa.co') }}/vendor/contacts" target="_blank"
                           class="group p-5 rounded-2xl glass hover:glass-light border border-white/5 hover:border-sanaa-cyan/30 transition-all duration-300 hover:-translate-y-1">
                            <div class="flex flex-col items-center gap-3">
                                <div class="w-12 h-12 rounded-2xl bg-sanaa-cyan/10 flex items-center justify-center text-sanaa-cyan group-hover:bg-sanaa-cyan group-hover:text-white transition-all shadow-lg shadow-sanaa-cyan/5 group-hover:shadow-sanaa-cyan/30">
                                    <x-heroicon-m-user-group class="w-6 h-6" />
                                </div>
                                <div class="text-center">
                                    <span class="text-xs font-bold text-white">Contacts</span>
                                    <p class="text-[8px] text-gray-500 font-medium uppercase tracking-wider mt-1">Manage All</p>
                                </div>
                            </div>
                        </a>

                        <a href="{{ config('services.whatsapp.admin_url', 'https://wa.sanaa.co') }}/vendor/campaigns" target="_blank"
                           class="group p-5 rounded-2xl glass hover:glass-light border border-white/5 hover:border-sanaa-indigo/30 transition-all duration-300 hover:-translate-y-1">
                            <div class="flex flex-col items-center gap-3">
                                <div class="w-12 h-12 rounded-2xl bg-sanaa-indigo/10 flex items-center justify-center text-sanaa-indigo group-hover:bg-sanaa-indigo group-hover:text-white transition-all shadow-lg shadow-sanaa-indigo/5 group-hover:shadow-sanaa-indigo/30">
                                    <x-heroicon-m-megaphone class="w-6 h-6" />
                                </div>
                                <div class="text-center">
                                    <span class="text-xs font-bold text-white">Campaigns</span>
                                    <p class="text-[8px] text-gray-500 font-medium uppercase tracking-wider mt-1">Broadcast</p>
                                </div>
                            </div>
                        </a>

                        <a href="{{ config('services.whatsapp.admin_url', 'https://wa.sanaa.co') }}/vendor/bot-flows" target="_blank"
                           class="group p-5 rounded-2xl glass hover:glass-light border border-white/5 hover:border-purple-500/30 transition-all duration-300 hover:-translate-y-1">
                            <div class="flex flex-col items-center gap-3">
                                <div class="w-12 h-12 rounded-2xl bg-purple-500/10 flex items-center justify-center text-purple-500 group-hover:bg-purple-500 group-hover:text-white transition-all shadow-lg shadow-purple-500/5 group-hover:shadow-purple-500/30">
                                    <x-heroicon-m-cpu-chip class="w-6 h-6" />
                                </div>
                                <div class="text-center">
                                    <span class="text-xs font-bold text-white">Bot Flows</span>
                                    <p class="text-[8px] text-gray-500 font-medium uppercase tracking-wider mt-1">AI Automation</p>
                                </div>
                            </div>
                        </a>
                    </div>
                </div>
            </div>
        </div>

        {{-- Setup Guide (shown when vendor not configured) --}}
        @if(empty($status['vendor_uid'] ?? '') || !($status['has_api_token'] ?? false))
            <div class="glass-dark rounded-[32px] p-8 shadow-2xl overflow-hidden relative">
                <div class="absolute -bottom-24 -right-24 w-48 h-48 bg-amber-500/5 blur-[80px] rounded-full"></div>
                <div class="relative z-10 space-y-6">
                    <div class="flex items-center gap-3 border-b border-white/5 pb-5">
                        <div class="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-500">
                            <x-heroicon-m-wrench-screwdriver class="w-5 h-5" />
                        </div>
                        <div>
                            <h3 class="text-[15px] font-black text-white">Setup Required</h3>
                            <p class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.12em]">Complete Configuration</p>
                        </div>
                    </div>

                    <div class="space-y-4">
                        <div class="flex items-start gap-4 p-4 rounded-xl glass border border-white/5">
                            <div class="w-8 h-8 rounded-lg {{ !empty($status['vendor_uid'] ?? '') ? 'bg-emerald-500/20 text-emerald-500' : 'bg-amber-500/20 text-amber-500' }} flex items-center justify-center flex-shrink-0 mt-0.5">
                                @if(!empty($status['vendor_uid'] ?? ''))
                                    <x-heroicon-m-check class="w-4 h-4" />
                                @else
                                    <span class="text-xs font-black">1</span>
                                @endif
                            </div>
                            <div>
                                <p class="text-sm font-bold text-white">Set Vendor UID</p>
                                <p class="text-xs text-gray-400 mt-1">Login to <a href="{{ config('services.whatsapp.admin_url', 'https://wa.sanaa.co') }}" target="_blank" class="text-sanaa-indigo hover:underline">wa.sanaa.co</a>, go to Vendor Settings, and copy your Vendor UID. Add it to <code class="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-sanaa-cyan">WHATSAPP_SAAS_VENDOR_UID</code> in your .env file.</p>
                            </div>
                        </div>

                        <div class="flex items-start gap-4 p-4 rounded-xl glass border border-white/5">
                            <div class="w-8 h-8 rounded-lg {{ ($status['has_api_token'] ?? false) ? 'bg-emerald-500/20 text-emerald-500' : 'bg-amber-500/20 text-amber-500' }} flex items-center justify-center flex-shrink-0 mt-0.5">
                                @if($status['has_api_token'] ?? false)
                                    <x-heroicon-m-check class="w-4 h-4" />
                                @else
                                    <span class="text-xs font-black">2</span>
                                @endif
                            </div>
                            <div>
                                <p class="text-sm font-bold text-white">Set API Token</p>
                                <p class="text-xs text-gray-400 mt-1">In WhatsJet vendor settings, generate an API token. Add it to <code class="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-sanaa-cyan">WHATSAPP_SAAS_API_TOKEN</code> in your .env file.</p>
                            </div>
                        </div>

                        <div class="flex items-start gap-4 p-4 rounded-xl glass border border-white/5">
                            <div class="w-8 h-8 rounded-lg bg-gray-500/20 text-gray-500 flex items-center justify-center flex-shrink-0 mt-0.5">
                                <span class="text-xs font-black">3</span>
                            </div>
                            <div>
                                <p class="text-sm font-bold text-white">Connect WhatsApp Business</p>
                                <p class="text-xs text-gray-400 mt-1">In WhatsJet, connect your Meta WhatsApp Business account with your phone number and configure templates.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        @endif
    </div>
</x-filament-panels::page>
