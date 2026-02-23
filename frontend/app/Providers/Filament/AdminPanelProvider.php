<?php

namespace App\Providers\Filament;

use Filament\Http\Middleware\Authenticate;
use Filament\Http\Middleware\AuthenticateSession;
use Filament\Http\Middleware\DisableBladeIconComponents;
use Filament\Http\Middleware\DispatchServingFilamentEvent;
use Filament\Pages;
use Filament\Panel;
use Filament\PanelProvider;
use Filament\Support\Colors\Color;
use Filament\Widgets;
use Illuminate\Cookie\Middleware\AddQueuedCookiesToResponse;
use Illuminate\Cookie\Middleware\EncryptCookies;
use Illuminate\Foundation\Http\Middleware\VerifyCsrfToken;
use Illuminate\Routing\Middleware\SubstituteBindings;
use Illuminate\Session\Middleware\StartSession;
use Illuminate\View\Middleware\ShareErrorsFromSession;

class AdminPanelProvider extends PanelProvider
{
    public function panel(Panel $panel): Panel
    {
        return $panel
            ->default()
            ->id('admin')
            ->path('/')
            ->login()
            ->brandName('Sanaa Intelligence')
            ->brandLogo(new \Illuminate\Support\HtmlString(view('components.sanaa-logo', ['class' => 'h-8'])->render()))
            ->darkModeBrandLogo(new \Illuminate\Support\HtmlString(view('components.sanaa-logo', ['class' => 'h-8'])->render()))
            ->brandLogoHeight('2rem')
            ->favicon(asset('favicon.ico'))
            ->colors([
                'primary' => [
                    50 => 'hsl(234, 89%, 96%)',
                    100 => 'hsl(234, 89%, 92%)',
                    200 => 'hsl(234, 89%, 84%)',
                    300 => 'hsl(234, 89%, 76%)',
                    400 => 'hsl(234, 89%, 70%)',
                    500 => 'hsl(234, 89%, 64%)',
                    600 => 'hsl(234, 89%, 58%)',
                    700 => 'hsl(234, 89%, 50%)',
                    800 => 'hsl(234, 89%, 42%)',
                    900 => 'hsl(234, 89%, 34%)',
                    950 => 'hsl(234, 89%, 24%)',
                ],
            ])
            ->font('Inter')
            ->darkMode(true)
            ->viteTheme('resources/css/app.css')
            ->sidebarCollapsibleOnDesktop()
            ->discoverResources(in: app_path('Filament/Resources'), for: 'App\\Filament\\Resources')
            ->discoverPages(in: app_path('Filament/Pages'), for: 'App\\Filament\\Pages')
            ->pages([
                \App\Filament\Pages\Dashboard::class,
            ])
            ->discoverWidgets(in: app_path('Filament/Widgets'), for: 'App\\Filament\\Widgets')
            ->widgets([
                // Dashboard widgets are managed in Dashboard page
            ])
            ->discoverWidgets(in: app_path('Filament/Widgets'), for: 'App\\Filament\\Widgets')
            ->widgets([
                // Dashboard widgets are managed in Dashboard page
            ])
            ->middleware([
                EncryptCookies::class,
                AddQueuedCookiesToResponse::class,
                StartSession::class,
                AuthenticateSession::class,
                ShareErrorsFromSession::class,
                VerifyCsrfToken::class,
                SubstituteBindings::class,
                DisableBladeIconComponents::class,
                DispatchServingFilamentEvent::class,
            ])
            ->authMiddleware([
                Authenticate::class,
            ])
            ->renderHook(
                \Filament\View\PanelsRenderHook::USER_MENU_BEFORE,
                fn (): string => \Illuminate\Support\Facades\Blade::render("@livewire('sanaa-fab')"),
            );
    }
}
