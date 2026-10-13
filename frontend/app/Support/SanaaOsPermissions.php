<?php

namespace App\Support;

class SanaaOsPermissions
{
    public static function roles(): array
    {
        return config('sanaa_os_permissions.roles', []);
    }

    public static function matrix(): array
    {
        return [
            'apps' => config('sanaa_os_permissions.apps', []),
            'settings_panes' => config('sanaa_os_permissions.settings_panes', []),
            'panel_prefix' => config('sanaa_os_permissions.panel_prefix', []),
            'actions' => config('sanaa_os_permissions.actions', []),
        ];
    }

    public static function canAccessApp(?string $role, string $appId): bool
    {
        $role = $role ?: 'viewer';
        $apps = config('sanaa_os_permissions.apps', []);

        if (isset($apps[$appId])) {
            return in_array($role, $apps[$appId], true);
        }

        if (str_starts_with($appId, 'panel-')) {
            $panels = config('sanaa_os_permissions.panel_prefix', []);
            if (isset($panels[$appId])) {
                return in_array($role, $panels[$appId], true);
            }
            $default = $panels['panel-'] ?? ['admin', 'operator', 'viewer'];

            return in_array($role, $default, true);
        }

        if (str_starts_with($appId, 'external-')) {
            return in_array($role, ['admin', 'operator', 'viewer'], true);
        }

        return in_array($role, ['admin', 'operator'], true);
    }

    public static function canAccessSettings(?string $role, string $paneId): bool
    {
        $role = $role ?: 'viewer';
        $panes = config('sanaa_os_permissions.settings_panes', []);

        if (! isset($panes[$paneId])) {
            return $role === 'admin';
        }

        return in_array($role, $panes[$paneId], true);
    }

    public static function canPerform(?string $role, string $action): bool
    {
        $role = $role ?: 'viewer';
        $actions = config('sanaa_os_permissions.actions', []);

        if (! isset($actions[$action])) {
            return $role === 'admin';
        }

        return in_array($role, $actions[$action], true);
    }

    public static function toJson(): array
    {
        return [
            'roles' => self::roles(),
            'matrix' => self::matrix(),
        ];
    }
}
