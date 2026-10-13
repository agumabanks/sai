<x-filament-panels::page class="relative">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#5e5ce6]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#ff9f0a]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-40"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#ff9f0a] to-[#ff453a] flex items-center justify-center shadow-lg shadow-[#ff9f0a]/20">
                    @svg('heroicon-o-users', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">User Management</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">Manage users and role-based access control</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#5e5ce6]"></span>
                    {{ count($this->users) }} Users
                </div>
                <x-filament::button size="sm" wire:click="openCreateModal" icon="heroicon-o-plus">
                    Add User
                </x-filament::button>
            </div>
        </div>

        {{-- ── Users Table ─────────────────────────────────────────────────── --}}
        <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)] overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead>
                        <tr class="border-b border-white/[0.06]">
                            <th class="px-5 py-3 text-left text-[11px] font-semibold text-white/40 uppercase tracking-wider">Name</th>
                            <th class="px-5 py-3 text-left text-[11px] font-semibold text-white/40 uppercase tracking-wider">Email</th>
                            <th class="px-5 py-3 text-left text-[11px] font-semibold text-white/40 uppercase tracking-wider">Role</th>
                            <th class="px-5 py-3 text-left text-[11px] font-semibold text-white/40 uppercase tracking-wider">Status</th>
                            <th class="px-5 py-3 text-left text-[11px] font-semibold text-white/40 uppercase tracking-wider">Created</th>
                            <th class="px-5 py-3 text-right text-[11px] font-semibold text-white/40 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-white/[0.04]">
                        @forelse($this->users as $u)
                            @php
                                $badge = $this->getRoleBadge($u['role'] ?? 'viewer');
                                $isDeleted = !empty($u['deleted_at']);
                            @endphp
                            <tr class="hover:bg-white/[0.02] transition-colors {{ $isDeleted ? 'opacity-50' : '' }}">
                                <td class="px-5 py-3">
                                    <div class="flex items-center gap-3">
                                        <div class="w-8 h-8 rounded-full bg-gradient-to-br from-[#5e5ce6]/30 to-[#0a84ff]/30 flex items-center justify-center text-xs font-bold text-white/70 border border-white/10">
                                            {{ strtoupper(substr($u['name'] ?? '?', 0, 1)) }}
                                        </div>
                                        <span class="text-sm font-medium text-white/85">{{ $u['name'] ?? 'Unknown' }}</span>
                                    </div>
                                </td>
                                <td class="px-5 py-3 text-sm text-white/50">{{ $u['email'] ?? '' }}</td>
                                <td class="px-5 py-3">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide {{ $badge['color'] }}">
                                        {{ $badge['label'] }}
                                    </span>
                                </td>
                                <td class="px-5 py-3">
                                    @if($isDeleted)
                                        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#ff453a]/10 text-[#ff453a] border border-[#ff453a]/20">
                                            <div class="w-1.5 h-1.5 rounded-full bg-[#ff453a]"></div>
                                            Deactivated
                                        </span>
                                    @else
                                        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#30d158]/10 text-[#30d158] border border-[#30d158]/20">
                                            <div class="w-1.5 h-1.5 rounded-full bg-[#30d158]"></div>
                                            Active
                                        </span>
                                    @endif
                                </td>
                                <td class="px-5 py-3 text-[11px] text-white/35">
                                    {{ $u['created_at'] ? \Carbon\Carbon::parse($u['created_at'])->format('M d, Y') : '—' }}
                                </td>
                                <td class="px-5 py-3">
                                    <div class="flex items-center justify-end gap-2">
                                        @if(!$isDeleted)
                                            <button
                                                wire:click="openEditModal({{ $u['id'] }})"
                                                class="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-[#5e5ce6]/10 text-[#5e5ce6] hover:bg-[#5e5ce6]/20 border border-[#5e5ce6]/20 transition-colors cursor-pointer"
                                            >
                                                @svg('heroicon-o-pencil-square', 'w-3 h-3')
                                                Edit
                                            </button>
                                            @if($u['id'] !== auth()->id())
                                                <button
                                                    wire:click="deleteUser({{ $u['id'] }})"
                                                    wire:confirm="Are you sure you want to deactivate this user?"
                                                    class="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-[#ff453a]/10 text-[#ff453a] hover:bg-[#ff453a]/20 border border-[#ff453a]/20 transition-colors cursor-pointer"
                                                >
                                                    @svg('heroicon-o-trash', 'w-3 h-3')
                                                    Delete
                                                </button>
                                            @endif
                                        @else
                                            <button
                                                wire:click="restoreUser({{ $u['id'] }})"
                                                class="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-[#30d158]/10 text-[#30d158] hover:bg-[#30d158]/20 border border-[#30d158]/20 transition-colors cursor-pointer"
                                            >
                                                @svg('heroicon-o-arrow-uturn-left', 'w-3 h-3')
                                                Restore
                                            </button>
                                        @endif
                                    </div>
                                </td>
                            </tr>
                        @empty
                            <tr>
                                <td colspan="6" class="px-5 py-12 text-center">
                                    @svg('heroicon-o-users', 'w-10 h-10 text-white/15 mx-auto mb-3')
                                    <p class="text-sm text-white/40">No users found</p>
                                </td>
                            </tr>
                        @endforelse
                    </tbody>
                </table>
            </div>
        </div>

        {{-- ── RBAC Overview ───────────────────────────────────────────────── --}}
        <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-[#5e5ce6] to-[#bf5af2] flex items-center justify-center shadow-lg">
                    @svg('heroicon-o-shield-check', 'w-5 h-5 text-white')
                </div>
                <div>
                    <h2 class="text-sm font-semibold text-white/90 tracking-tight">Role-Based Access Control</h2>
                    <p class="text-[10px] text-white/35 font-medium">Permission matrix for each role</p>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                {{-- Admin --}}
                <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
                    <div class="flex items-center gap-2 mb-3">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20">
                            Admin
                        </span>
                    </div>
                    <ul class="space-y-1.5 text-[11px] text-white/50">
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') Full access to all pages</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') Manage users and roles</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') System settings access</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') Create, edit, delete actions</li>
                    </ul>
                </div>

                {{-- Operator --}}
                <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
                    <div class="flex items-center gap-2 mb-3">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide text-[#5e5ce6] bg-[#5e5ce6]/10 border-[#5e5ce6]/20">
                            Operator
                        </span>
                    </div>
                    <ul class="space-y-1.5 text-[11px] text-white/50">
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') Access most pages</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') Perform actions (create, edit)</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-x-circle', 'w-3.5 h-3.5 text-[#ff453a]') No Settings access</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-x-circle', 'w-3.5 h-3.5 text-[#ff453a]') No User Management access</li>
                    </ul>
                </div>

                {{-- Viewer --}}
                <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
                    <div class="flex items-center gap-2 mb-3">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20">
                            Viewer
                        </span>
                    </div>
                    <ul class="space-y-1.5 text-[11px] text-white/50">
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') View all non-settings pages</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-check-circle', 'w-3.5 h-3.5 text-[#30d158]') Read-only access</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-x-circle', 'w-3.5 h-3.5 text-[#ff453a]') No Settings access</li>
                        <li class="flex items-center gap-2">@svg('heroicon-o-x-circle', 'w-3.5 h-3.5 text-[#ff453a]') No action buttons</li>
                    </ul>
                </div>
            </div>
        </div>

    </div>

    {{-- ── Create User Modal ────────────────────────────────────────────── --}}
    @if($this->showCreateModal)
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" wire:click.self="closeCreateModal">
            <div class="bg-[#1c1c1e] border border-white/[0.10] rounded-2xl p-6 w-full max-w-md shadow-2xl">
                <h3 class="text-lg font-semibold text-white/90 mb-4">Create New User</h3>

                <div class="space-y-4">
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Name</label>
                        <input type="text" wire:model="createName" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 placeholder-white/25 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors" placeholder="Full name">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Email</label>
                        <input type="email" wire:model="createEmail" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 placeholder-white/25 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors" placeholder="user@example.com">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Password</label>
                        <input type="password" wire:model="createPassword" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 placeholder-white/25 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors" placeholder="Min 8 characters">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Role</label>
                        <select wire:model="createRole" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors">
                            <option value="admin" class="bg-[#1c1c1e]">Admin</option>
                            <option value="operator" class="bg-[#1c1c1e]">Operator</option>
                            <option value="viewer" class="bg-[#1c1c1e]">Viewer</option>
                            <option value="seller" class="bg-[#1c1c1e]">Seller</option>
                        </select>
                    </div>
                </div>

                <div class="flex items-center justify-end gap-3 mt-6">
                    <button wire:click="closeCreateModal" class="px-4 py-2 rounded-xl text-sm font-medium text-white/50 bg-white/[0.05] border border-white/[0.08] hover:bg-white/[0.08] transition-colors cursor-pointer">
                        Cancel
                    </button>
                    <button wire:click="createUser" class="px-4 py-2 rounded-xl text-sm font-medium text-white bg-gradient-to-r from-[#5e5ce6] to-[#0a84ff] hover:opacity-90 transition-opacity cursor-pointer">
                        Create User
                    </button>
                </div>
            </div>
        </div>
    @endif

    {{-- ── Edit User Modal ──────────────────────────────────────────────── --}}
    @if($this->showEditModal)
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" wire:click.self="closeEditModal">
            <div class="bg-[#1c1c1e] border border-white/[0.10] rounded-2xl p-6 w-full max-w-md shadow-2xl">
                <h3 class="text-lg font-semibold text-white/90 mb-4">Edit User</h3>

                <div class="space-y-4">
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Name</label>
                        <input type="text" wire:model="editName" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 placeholder-white/25 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Email</label>
                        <input type="email" wire:model="editEmail" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 placeholder-white/25 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Password (leave blank to keep)</label>
                        <input type="password" wire:model="editPassword" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 placeholder-white/25 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors" placeholder="Leave blank to keep current">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-white/50 mb-1.5 uppercase tracking-wider">Role</label>
                        <select wire:model="editRole" class="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-4 py-2.5 text-sm text-white/90 focus:border-[#5e5ce6]/50 focus:ring-1 focus:ring-[#5e5ce6]/30 outline-none transition-colors">
                            <option value="admin" class="bg-[#1c1c1e]">Admin</option>
                            <option value="operator" class="bg-[#1c1c1e]">Operator</option>
                            <option value="viewer" class="bg-[#1c1c1e]">Viewer</option>
                            <option value="seller" class="bg-[#1c1c1e]">Seller</option>
                        </select>
                    </div>
                </div>

                <div class="flex items-center justify-end gap-3 mt-6">
                    <button wire:click="closeEditModal" class="px-4 py-2 rounded-xl text-sm font-medium text-white/50 bg-white/[0.05] border border-white/[0.08] hover:bg-white/[0.08] transition-colors cursor-pointer">
                        Cancel
                    </button>
                    <button wire:click="updateUser" class="px-4 py-2 rounded-xl text-sm font-medium text-white bg-gradient-to-r from-[#5e5ce6] to-[#0a84ff] hover:opacity-90 transition-opacity cursor-pointer">
                        Save Changes
                    </button>
                </div>
            </div>
        </div>
    @endif
</x-filament-panels::page>
