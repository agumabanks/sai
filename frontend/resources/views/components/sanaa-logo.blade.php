@props(['class' => 'h-8'])
<div {{ $attributes->merge(['class' => $class . ' flex items-center gap-2.5']) }}>
    <svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" class="h-full w-auto shrink-0">
        {{-- Outer ring --}}
        <circle cx="18" cy="18" r="17" stroke="url(#logoGrad)" stroke-width="1.5" opacity="0.6"/>
        {{-- Inner glow disc --}}
        <circle cx="18" cy="18" r="12" fill="url(#logoFill)" opacity="0.12"/>
        {{-- S monogram --}}
        <path d="M21.5 13.5c0-1.5-1.2-2.5-3.5-2.5s-3.5 1-3.5 2.5c0 1.8 1.8 2.2 3.5 2.8 1.7.6 3.5 1.2 3.5 3.2 0 1.8-1.5 3-3.5 3s-3.5-1.2-3.5-3" 
              stroke="url(#logoGrad)" stroke-width="2" stroke-linecap="round" fill="none"/>
        <defs>
            <linearGradient id="logoGrad" x1="0" y1="0" x2="36" y2="36">
                <stop offset="0%" stop-color="hsl(234, 89%, 64%)"/>
                <stop offset="100%" stop-color="hsl(262, 83%, 65%)"/>
            </linearGradient>
            <radialGradient id="logoFill" cx="0.5" cy="0.5" r="0.5">
                <stop offset="0%" stop-color="hsl(234, 89%, 64%)"/>
                <stop offset="100%" stop-color="hsl(262, 83%, 65%)" stop-opacity="0"/>
            </radialGradient>
        </defs>
    </svg>
    <span class="text-sm font-black text-white tracking-tight whitespace-nowrap">Sanaa<span class="text-gray-500 font-medium ml-1">Intelligence</span></span>
</div>
