<?php

namespace App\Support;

class SanaaModules
{
    public static function all(): array
    {
        return array_map(fn (array $module): array => self::hydrate($module), self::definitions());
    }

    public static function dashboardTiles(): array
    {
        $modules = collect(self::all())->keyBy('id');
        $moduleTiles = collect([
            'brain',
            'skills',
            'intelligence',
            'watch',
            'channels',
            'devices',
        ])->map(fn (string $id) => $modules->get($id))->filter()->values();

        $featureTiles = collect(SanaaOsFeatures::dashboardTiles())
            ->reject(fn (array $tile) => $moduleTiles->contains(fn (?array $module) => ($module['id'] ?? null) === $tile['id']));

        return $moduleTiles
            ->merge($featureTiles)
            ->filter()
            ->values()
            ->all();
    }

    private static function definitions(): array
    {
        return [
            [
                'id' => 'overview',
                'label' => 'Dashboard',
                'short_label' => 'Home',
                'description' => 'Command overview',
                'icon' => 'heroicon-m-home',
                'accent' => '#4285f4',
                'route' => 'filament.admin.pages.dashboard',
                'groups' => [''],
                'paths' => SanaaOsFeatures::pathsForModule('overview'),
            ],
            [
                'id' => 'brain',
                'label' => 'Sanaa Brain',
                'short_label' => 'Brain',
                'description' => 'AI engine',
                'icon' => 'heroicon-m-cpu-chip',
                'accent' => '#8b5cf6',
                'route' => 'filament.admin.pages.ai-brain-settings',
                'groups' => ['Settings'],
                'paths' => SanaaOsFeatures::pathsForModule('brain'),
            ],
            [
                'id' => 'skills',
                'label' => 'Sanaa Skills',
                'short_label' => 'Skills',
                'description' => 'Tools and workflows',
                'icon' => 'heroicon-m-bolt',
                'accent' => '#f59e0b',
                'route' => 'filament.admin.pages.skills-command-center',
                'groups' => ['Skills Lab'],
                'paths' => SanaaOsFeatures::pathsForModule('skills'),
            ],
            [
                'id' => 'intelligence',
                'label' => 'Sanaa Intel',
                'short_label' => 'Intel',
                'description' => 'Signals and memory',
                'icon' => 'heroicon-m-presentation-chart-line',
                'accent' => '#0ea5e9',
                'route' => 'filament.admin.pages.strategic-command',
                'groups' => ['Intelligence'],
                'paths' => SanaaOsFeatures::pathsForModule('intelligence'),
            ],
            [
                'id' => 'watch',
                'label' => 'Sanaa Watch',
                'short_label' => 'Watch',
                'description' => 'System guard',
                'icon' => 'heroicon-m-shield-check',
                'accent' => '#10b981',
                'route' => 'filament.admin.pages.system-doctor',
                'groups' => ['System'],
                'paths' => SanaaOsFeatures::pathsForModule('watch'),
            ],
            [
                'id' => 'channels',
                'label' => 'Sanaa Chat',
                'short_label' => 'Chat',
                'description' => 'Groq command chat',
                'icon' => 'heroicon-m-chat-bubble-left-right',
                'accent' => '#2563eb',
                'route' => 'filament.admin.pages.sanaa-chat',
                'groups' => ['', 'Channels'],
                'paths' => SanaaOsFeatures::pathsForModule('channels'),
            ],
            [
                'id' => 'infrastructure',
                'label' => 'Sanaa Ops',
                'short_label' => 'Ops',
                'description' => 'Sites and tenants',
                'icon' => 'heroicon-m-server-stack',
                'accent' => '#14b8a6',
                'route' => 'filament.admin.pages.platform-command-center',
                'groups' => ['Infrastructure'],
                'paths' => SanaaOsFeatures::pathsForModule('infrastructure'),
            ],
            [
                'id' => 'devices',
                'label' => 'Device Army',
                'short_label' => 'Devices',
                'description' => 'Connected devices',
                'icon' => 'heroicon-m-device-phone-mobile',
                'accent' => '#a855f7',
                'route' => 'filament.admin.pages.device-army-dashboard',
                'groups' => ['Device Army'],
                'paths' => SanaaOsFeatures::pathsForModule('devices'),
            ],
            [
                'id' => 'licenses',
                'label' => 'Sanaa Licenses',
                'short_label' => 'Licenses',
                'description' => 'Plans and tenants',
                'icon' => 'heroicon-m-key',
                'accent' => '#64748b',
                'route' => 'filament.admin.resources.sanaa-license-tenants.index',
                'groups' => ['License Management'],
                'paths' => SanaaOsFeatures::pathsForModule('licenses'),
            ],
            [
                'id' => 'marketing',
                'label' => 'Sanaa Growth',
                'short_label' => 'Growth',
                'description' => 'Campaigns',
                'icon' => 'heroicon-m-megaphone',
                'accent' => '#ef4444',
                'route' => 'filament.admin.pages.marketing-dashboard',
                'groups' => ['Marketing'],
                'paths' => SanaaOsFeatures::pathsForModule('marketing'),
            ],
        ];
    }

    private static function hydrate(array $module): array
    {
        $url = route($module['route']);
        $path = parse_url($url, PHP_URL_PATH) ?: '/';

        return [
            ...$module,
            'url' => $url,
            'paths' => array_values(array_unique([...($module['paths'] ?? []), $path])),
        ];
    }
}
