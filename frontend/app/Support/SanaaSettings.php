<?php

namespace App\Support;

class SanaaSettings
{
    public static function groups(): array
    {
        return config('sanaa_settings.groups', []);
    }

    public static function panes(): array
    {
        return collect(config('sanaa_settings.panes', []))
            ->sortBy('sort')
            ->map(fn (array $pane): array => self::hydratePane($pane))
            ->values()
            ->all();
    }

    public static function controlCenter(): array
    {
        $cc = config('sanaa_settings.control_center', []);

        return [
            'toggles' => $cc['toggles'] ?? [],
            'modules' => collect($cc['modules'] ?? [])->map(function (array $module): array {
                if (! empty($module['filament_path'])) {
                    $module['url'] = url(SanaaOsFeatures::filamentPath($module['filament_path']));
                }

                return $module;
            })->values()->all(),
        ];
    }

    public static function launcher(): array
    {
        return config('sanaa_settings.launcher', []);
    }

    public static function menubar(): array
    {
        return config('sanaa_settings.menubar', []);
    }

    public static function toJson(): array
    {
        return [
            'version' => config('sanaa_settings.version', '1.0'),
            'groups' => self::groups(),
            'panes' => self::panes(),
            'control_center' => self::controlCenter(),
            'launcher' => self::launcher(),
            'menubar' => self::menubar(),
            'wallpapers' => self::wallpapers(),
            'urls' => [
                'admin' => url('/'),
                'os' => url('/'),
                'doctor' => route('filament.admin.pages.sanaa-doctor'),
                'device_army' => route('filament.admin.pages.device-army-dashboard'),
            ],
        ];
    }

    public static function wallpapers(): array
    {
        return [
            ['id' => 'default', 'name' => 'Sanaa Dark', 'category' => 'sanaa', 'type' => 'gradient', 'is_uploadable' => false],
            ['id' => 'ventura', 'name' => 'Ventura', 'category' => 'gradients', 'type' => 'gradient', 'is_uploadable' => false],
            ['id' => 'monterey', 'name' => 'Monterey', 'category' => 'gradients', 'type' => 'gradient', 'is_uploadable' => false],
            ['id' => 'aurora', 'name' => 'Aurora', 'category' => 'abstract', 'type' => 'gradient', 'is_uploadable' => false],
            ['id' => 'space', 'name' => 'Deep Space', 'category' => 'space', 'type' => 'gradient', 'is_uploadable' => false],
            ['id' => 'light', 'name' => 'Minimal Light', 'category' => 'abstract', 'type' => 'gradient', 'is_uploadable' => false],
            ['id' => 'cyber', 'name' => 'Cyberpunk', 'category' => 'abstract', 'type' => 'gradient', 'is_uploadable' => false],
            ['id' => 'dynamic-coast', 'name' => 'Coastline', 'category' => 'dynamic', 'type' => 'dynamic', 'is_uploadable' => false],
        ];
    }

    private static function hydratePane(array $pane): array
    {
        if (! empty($pane['filament_path'])) {
            $pane['url'] = url(SanaaOsFeatures::filamentPath($pane['filament_path']));
        }

        return $pane;
    }
}
