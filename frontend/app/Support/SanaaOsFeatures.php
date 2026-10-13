<?php

namespace App\Support;

class SanaaOsFeatures
{
    public static function modules(): array
    {
        return config('sanaa_os_features.modules', []);
    }

    public static function all(): array
    {
        return array_map(
            fn (array $feature): array => self::hydrate($feature),
            config('sanaa_os_features.features', []),
        );
    }

    public static function filamentPages(): array
    {
        return collect(self::all())
            ->filter(fn (array $f): bool => ($f['type'] ?? '') === 'filament' && ! empty($f['path']))
            ->sortBy('label')
            ->values()
            ->map(fn (array $f): array => [
                'id' => $f['id'],
                'label' => $f['label'],
                'path' => $f['path'],
                'module' => $f['module'] ?? null,
            ])
            ->all();
    }

    public static function desktopShortcuts(): array
    {
        return collect(self::all())
            ->filter(fn (array $f): bool => (bool) ($f['desktop'] ?? false))
            ->sortBy(fn (array $f) => (int) ($f['sort'] ?? 100))
            ->map(fn (array $f): array => [
                'id' => $f['id'],
                'label' => $f['label'],
                'app' => self::appIdForFeature($f),
                'module' => $f['module'] ?? null,
                'category' => $f['category'] ?? 'ai',
                'external' => (bool) ($f['external'] ?? ($f['type'] ?? '') === 'external'),
                'url' => $f['url'] ?? null,
            ])
            ->values()
            ->all();
    }

    public static function dashboardTiles(): array
    {
        return collect(self::all())
            ->filter(fn (array $f): bool => (bool) ($f['dashboard_tile'] ?? false))
            ->sortBy(fn (array $f) => (int) ($f['sort'] ?? 100))
            ->map(fn (array $f): array => [
                'id' => $f['id'],
                'label' => $f['dashboard_label'] ?? $f['label'],
                'short_label' => $f['dashboard_short'] ?? $f['label'],
                'description' => $f['dashboard_description'] ?? ($f['description'] ?? ''),
                'icon' => $f['dashboard_icon'] ?? 'heroicon-m-squares-2x2',
                'accent' => $f['dashboard_accent'] ?? ($f['module_accent'] ?? '#6366f1'),
                'url' => $f['url'] ?? url($f['path'] ?? '/'),
                'external' => (bool) ($f['external'] ?? ($f['type'] ?? '') === 'external'),
                'paths' => ! empty($f['path']) ? [$f['path']] : [],
            ])
            ->values()
            ->all();
    }

    public static function pinnedAppIds(): array
    {
        return collect(config('sanaa_os_features.core_pins', []))
            ->unique()
            ->values()
            ->all();
    }

    public static function quickLaunch(): array
    {
        return collect(self::all())
            ->filter(fn (array $f): bool => (bool) ($f['quick_launch'] ?? false))
            ->sortBy(fn (array $f) => (int) ($f['sort'] ?? 100))
            ->take((int) config('sanaa_os_features.dock.max_shortcuts', 12))
            ->map(fn (array $f): array => [
                'id' => $f['id'],
                'label' => $f['label'],
                'description' => $f['description'] ?? ($f['module_label'] ?? ''),
                'accent' => $f['module_accent'] ?? '#6366f1',
                'icon' => $f['icon'] ?? 'brain',
                'app_id' => self::appIdForFeature($f),
                'url' => $f['url'] ?? null,
                'external' => (bool) ($f['external'] ?? ($f['type'] ?? '') === 'external'),
            ])
            ->values()
            ->all();
    }

    public static function pathsForModule(string $moduleId): array
    {
        return collect(self::all())
            ->filter(fn (array $f): bool => ($f['module'] ?? '') === $moduleId && ! empty($f['path']))
            ->pluck('path')
            ->unique()
            ->values()
            ->all();
    }

    public static function toJson(): array
    {
        return [
            'version' => 1,
            'os_url' => url('/'),
            'admin_url' => url('/'),
            'modules' => self::modules(),
            'features' => self::all(),
            'filament_pages' => self::filamentPages(),
            'desktop_shortcuts' => self::desktopShortcuts(),
            'pinned_apps' => self::pinnedAppIds(),
            'quick_launch' => self::quickLaunch(),
            'dock' => config('sanaa_os_features.dock', []),
            'core_pins' => config('sanaa_os_features.core_pins', []),
        ];
    }

    public static function appIdForFeature(array $feature): string
    {
        return match ($feature['type'] ?? '') {
            'native' => $feature['native_app'] ?? $feature['id'],
            'external' => 'external-'.($feature['id'] ?? 'link'),
            default => 'panel-'.($feature['id'] ?? 'feature'),
        };
    }

    public static function filamentPath(?string $path): ?string
    {
        if ($path === null || $path === '') {
            return null;
        }

        $normalized = '/'.trim($path, '/');
        if ($normalized === '/admin' || str_starts_with($normalized, '/admin/')) {
            return $normalized;
        }

        return '/admin'.$normalized;
    }

    private static function hydrate(array $feature): array
    {
        $module = $feature['module'] ?? null;
        $moduleMeta = $module ? (self::modules()[$module] ?? []) : [];
        $path = $feature['path'] ?? null;

        if (($feature['type'] ?? '') === 'filament' && $path) {
            $path = self::filamentPath($path);
        }

        return [
            ...$feature,
            'path' => $path,
            'module_label' => $moduleMeta['label'] ?? null,
            'module_accent' => $moduleMeta['accent'] ?? null,
            'url' => $path ? url($path) : null,
        ];
    }
}
