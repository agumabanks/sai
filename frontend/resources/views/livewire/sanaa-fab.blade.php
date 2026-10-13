@php
    $modules = \App\Support\SanaaModules::all();
@endphp

<x-sanaa-module-shell-script :modules="$modules" />

<div
    class="relative"
    x-data="sanaaAppLauncher"
    x-on:keydown.escape.window="open = false"
    x-on:resize.window.debounce.100ms="positionPanel()"
    wire:ignore
>
    <button
        x-ref="trigger"
        type="button"
        class="sanaa-launcher-trigger"
        x-on:click="toggle()"
        x-bind:aria-expanded="open.toString()"
        aria-label="Open Sanaa apps"
    >
        <span class="sanaa-launcher-dots" aria-hidden="true">
            @for ($i = 0; $i < 9; $i++)
                <span></span>
            @endfor
        </span>
    </button>

    <div
        x-ref="panel"
        x-show="open"
        x-on:click="open = false"
        x-transition.opacity.duration.100ms
        class="fixed inset-0 z-40 bg-transparent"
        style="display: none;"
    ></div>

    <div
        x-show="open"
        x-transition:enter="transition ease-out duration-150"
        x-transition:enter-start="opacity-0 scale-95 translate-y-1"
        x-transition:enter-end="opacity-100 scale-100 translate-y-0"
        x-transition:leave="transition ease-in duration-100"
        x-transition:leave-start="opacity-100 scale-100 translate-y-0"
        x-transition:leave-end="opacity-0 scale-95 translate-y-1"
        x-on:click.outside="open = false"
        x-bind:style="open ? { '--sanaa-launcher-left': `${panelLeft}px`, '--sanaa-launcher-top': `${panelTop}px` } : {}"
        class="sanaa-launcher-panel"
        style="display: none;"
    >
        <div class="sanaa-launcher-header">
            <div>
                <p>Sanaa apps</p>
                <span x-text="activeModule?.label || 'Dashboard'"></span>
            </div>
            <span class="sanaa-launcher-active-chip" x-text="activeModule?.short_label || 'Home'"></span>
        </div>

        <div class="sanaa-launcher-grid">
            @foreach ($modules as $module)
                <a
                    href="{{ $module['url'] }}"
                    class="sanaa-launcher-app"
                    x-bind:class="{ 'is-active': moduleIsActive('{{ $module['id'] }}') }"
                    x-on:click="selectModule('{{ $module['id'] }}', false)"
                >
                    <span class="sanaa-launcher-app-icon" style="--sanaa-module-accent: {{ $module['accent'] }}">
                        <x-dynamic-component :component="$module['icon']" class="h-6 w-6" />
                    </span>
                    <span class="sanaa-launcher-app-label">{{ $module['short_label'] }}</span>
                </a>
            @endforeach
        </div>
    </div>
</div>
