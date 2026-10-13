@php
    $modules = \App\Support\SanaaModules::all();
@endphp

<x-sanaa-module-shell-script :modules="$modules" />

<div
    x-data="sanaaSidebarModuleMenu"
    class="sanaa-sidebar-module-shell"
>
    @foreach ($modules as $module)
        <div
            class="sanaa-sidebar-module-card"
            x-show="activeModuleId === '{{ $module['id'] }}'"
            style="--sanaa-module-accent: {{ $module['accent'] }}; display: none;"
        >
            <div class="sanaa-sidebar-module-icon">
                <x-dynamic-component :component="$module['icon']" class="h-5 w-5" />
            </div>
            <div class="min-w-0">
                <p>{{ $module['label'] }}</p>
                <span>{{ $module['description'] }}</span>
            </div>
        </div>
    @endforeach
</div>
