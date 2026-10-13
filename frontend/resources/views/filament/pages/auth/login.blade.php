<div class="sanaa-login-page">
    {{-- Ambient Background --}}
    <div class="sanaa-login-bg">
        <div class="sanaa-login-bg-base"></div>
        <div class="sanaa-login-orb sanaa-login-orb--violet"></div>
        <div class="sanaa-login-orb sanaa-login-orb--blue"></div>
        <div class="sanaa-login-orb sanaa-login-orb--rose"></div>
    </div>

    {{-- Login Card --}}
    <div class="sanaa-login-card animate-scale-in">
        {{-- Logo --}}
        <div class="sanaa-login-logo">
            <x-sanaa-logo class="h-10" />
        </div>

        {{-- Tagline --}}
        <p class="sanaa-login-tagline">Autonomous Operations Platform</p>

        {{-- Divider --}}
        <div class="sanaa-login-divider"></div>

        {{-- Heading --}}
        <h2 class="sanaa-login-heading">Sign in to your account</h2>

        {{-- Form --}}
        <x-filament-panels::form id="form" wire:submit="authenticate">
            {{ $this->form }}

            <x-filament-panels::form.actions
                :actions="$this->getCachedFormActions()"
                :full-width="$this->hasFullWidthFormActions()"
            />
        </x-filament-panels::form>
    </div>

    {{-- Footer --}}
    <div class="sanaa-login-footer">
        <span>Sanaa Intelligence</span>
        <span class="sanaa-login-footer-dot">·</span>
        <span>Secured Access</span>
    </div>
</div>
