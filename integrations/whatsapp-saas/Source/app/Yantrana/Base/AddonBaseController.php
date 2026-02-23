<?php
/**
 * WhatsJet
 *
 * This file is part of the WhatsJet software package developed and licensed by livelyworks.
 *
 * You must have a valid license to use this software.
 *
 * © 2025 livelyworks. All rights reserved.
 * Redistribution or resale of this file, in whole or in part, is prohibited without prior written permission from the author.
 *
 * For support or inquiries, contact: contact@livelyworks.net
 *
 * @package     WhatsJet
 * @author      livelyworks <contact@livelyworks.net>
 * @copyright   Copyright (c) 2025, livelyworks
 * @website     https://livelyworks.net
 */


namespace App\Yantrana\Base;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\File;
use App\Yantrana\Base\BaseController;
use App\Yantrana\Base\BaseRequestTwo;
use Illuminate\Support\Facades\Response;
use App\Yantrana\Components\Configuration\Requests\ConfigurationRequest;

class AddonBaseController extends BaseController
{
    /**
     * Addon Namespace
     *
     * @var string
     */
    protected $addonNamespace = "AddonNamespace";
    /**
     * Show Addon Settings Page
     *
     * @return view
     */
    public function showSettings()
    {
        validateVendorAccess('administrative');
        return $this->addonView('settings');
    }

    /**
     * Get Addon Base Path
     *
     * @param string $path
     * @return string
     */
    function addonBasePath($path = '')
    {
        return base_path('addons' . DIRECTORY_SEPARATOR . $this->addonNamespace . DIRECTORY_SEPARATOR . $path);
    }
    /**
     * Serve addon assets.
     *
     * @param Request $request
     * @param string $path
     * @return \Illuminate\Http\Response|\Illuminate\Http\JsonResponse
     */
    public function assetServe(BaseRequestTwo $request, $path)
    {
        $file = $this->addonBasePath('assets' . DIRECTORY_SEPARATOR . $path);
        if (!File::exists($file)) {
            abort(404, 'Asset not found.');
        }
        $mimeType = File::mimeType($file);
        return Response::make(File::get($file), 200, ['Content-Type' => $mimeType]);
    }

    /**
     * Activate Addon View
     *
     * @return view
     */
    public function setupView()
    {
        return $this->addonView('setup', [
            'addonMetadata' => $this->addonMetadata(),
            'addon' => $this->addonNamespace,
            'addonLicInfo' => function ($item) {
                return $this->getAddonLicInfo($item);
            },
        ]);
    }

    /**
     * Base Addon View method
     *
     * @param string $viewName
     * @param array $parameters
     * @return view
     */
    public function addonView($viewName, $parameters = [])
    {
        return view("{$this->addonNamespace}::$viewName", $parameters);
    }

    /**
     * Addon Metadata
     *
     * @return array
     */
    public function addonMetadata()
    {
        $metadataPath = $this->addonBasePath('/config/metadata.php');
        if (File::exists($metadataPath)) {
            $content = File::get($metadataPath);
            if (preg_match("/(['\"])identifier(['\"])\s*=>\s*(['\"])([^'\"]+)(['\"])/", $content, $matches)) {
                return [
                    'identifier' => $matches[4]
                ];
            }
        }
        return [];
    }

    /**
     * Get addon lic info
     *
     * @param string $item
     * @return mixed
     */
    public function getAddonLicInfo($item = null)
    {
        return getAppSettings('lwAddon' . $this->addonNamespace, $item);
    }

    /**
     * Process addon reg
     *
     * @param  array  $inputData
     * @return mixed
     *---------------------------------------------------------------- */
    public function processAddonActivation(ConfigurationRequest $request)
    {
        return $this->processResponse(1, [], [
            'show_message' => true,
        ], true);
    }

    /**
     * Process addon reg remove
     *
     *
     * @return response
     *---------------------------------------------------------------- */
    public function processAddonDeactivation(ConfigurationRequest $request)
    {
        return $this->processResponse(1, [], [
            'show_message' => true,
        ], true);
    }
}
