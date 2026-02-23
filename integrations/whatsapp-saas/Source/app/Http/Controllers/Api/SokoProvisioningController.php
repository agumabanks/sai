<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Yantrana\Components\Auth\AuthEngine;
use App\Yantrana\Components\Vendor\Models\VendorModel;
use App\Yantrana\Components\Vendor\Models\VendorSettingsModel;
use App\Yantrana\Components\Auth\Models\AuthModel;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Illuminate\Support\Facades\Validator;

class SokoProvisioningController extends Controller
{
    protected AuthEngine $authEngine;

    public function __construct(AuthEngine $authEngine)
    {
        $this->authEngine = $authEngine;
    }

    /**
     * Provision a WhatsJet vendor for a Soko seller.
     * Idempotent — returns existing vendor if seller_uuid already provisioned.
     *
     * POST /api/soko/provision-vendor
     */
    public function provisionVendor(Request $request)
    {
        // Verify provisioning key
        $token = $request->bearerToken();
        if (!$token || $token !== config('services.soko_provision_key')) {
            return response()->json(['success' => false, 'message' => 'Unauthorized'], 401);
        }

        $validator = Validator::make($request->all(), [
            'seller_uuid' => 'required|string|max:36',
            'vendor_title' => 'required|string|min:2|max:100',
            'username' => 'required|string|max:50',
            'first_name' => 'required|string|max:50',
            'last_name' => 'nullable|string|max:50',
            'email' => 'required|email|max:255',
            'mobile_number' => 'nullable|string|min:9|max:15',
            'password' => 'nullable|string|min:8',
        ]);

        if ($validator->fails()) {
            return response()->json([
                'success' => false,
                'message' => $validator->errors()->first(),
            ], 422);
        }

        $sellerUuid = $request->input('seller_uuid');

        // Check if already provisioned (idempotent)
        $existing = $this->findVendorBySellerUuid($sellerUuid);
        if ($existing) {
            $apiToken = $this->getVendorApiToken($existing->_id);
            return response()->json([
                'success' => true,
                'already_existed' => true,
                'vendor_uid' => $existing->_uid,
                'vendor_api_token' => $apiToken,
                'seller_uuid' => $sellerUuid,
            ]);
        }

        // Check for email uniqueness in WhatsJet users
        $existingEmail = AuthModel::where('email', $request->input('email'))->first();
        if ($existingEmail) {
            // Use a unique email variant
            $email = 'soko_' . $sellerUuid . '@sanaa.co';
        } else {
            $email = $request->input('email');
        }

        // Ensure username is unique
        $baseUsername = Str::lower(Str::slug($request->input('username'), '_'));
        $username = $baseUsername;
        $counter = 1;
        while (AuthModel::where('username', $username)->exists()) {
            $username = $baseUsername . '_' . $counter;
            $counter++;
        }

        // Generate password if not provided
        $password = $request->input('password', Str::random(16));

        // Create vendor via AuthEngine
        $mobileNumber = $request->input('mobile_number');
        if (empty($mobileNumber)) {
            // Generate a placeholder phone based on seller ID to ensure uniqueness
            $mobileNumber = '256700' . str_pad(substr(crc32($sellerUuid), 0, 6), 6, '0', STR_PAD_LEFT);
        }

        $inputData = [
            'vendor_title' => $request->input('vendor_title'),
            'username' => $username,
            'first_name' => $request->input('first_name'),
            'last_name' => $request->input('last_name', 'Seller'),
            'email' => $email,
            'mobile_number' => $mobileNumber,
            'password' => $password,
            'password_confirmation' => $password,
        ];

        $response = $this->authEngine->processRegistration($inputData);

        if ($response->failed()) {
            return response()->json([
                'success' => false,
                'message' => 'Failed to create vendor: ' . ($response->message() ?? 'Unknown error'),
            ], 500);
        }

        // Find the newly created vendor by slug
        $vendor = VendorModel::where('slug', $username)->first();
        if (!$vendor) {
            return response()->json([
                'success' => false,
                'message' => 'Vendor created but could not be found',
            ], 500);
        }

        // Store seller_uuid in vendor_settings for cross-reference
        $this->storeVendorSetting($vendor->_id, 'soko_seller_uuid', $sellerUuid);

        // Generate and store an API access token
        $apiToken = Str::random(64);
        $this->storeVendorSetting($vendor->_id, 'vendor_api_access_token', $apiToken);

        return response()->json([
            'success' => true,
            'already_existed' => false,
            'vendor_uid' => $vendor->_uid,
            'vendor_api_token' => $apiToken,
            'seller_uuid' => $sellerUuid,
        ], 201);
    }

    /**
     * Get vendor details by seller_uuid.
     *
     * GET /api/soko/vendor/{sellerUuid}
     */
    public function getVendor(Request $request, string $sellerUuid)
    {
        $token = $request->bearerToken();
        if (!$token || $token !== config('services.soko_provision_key')) {
            return response()->json(['success' => false, 'message' => 'Unauthorized'], 401);
        }

        $vendor = $this->findVendorBySellerUuid($sellerUuid);
        if (!$vendor) {
            return response()->json([
                'success' => false,
                'message' => 'Vendor not found for this seller',
            ], 404);
        }

        $admin = AuthModel::where('vendors__id', $vendor->_id)->first();
        $apiToken = $this->getVendorApiToken($vendor->_id);

        return response()->json([
            'success' => true,
            'vendor' => [
                'uid' => $vendor->_uid,
                'title' => $vendor->title,
                'slug' => $vendor->slug,
                'status' => $vendor->status,
                'created_at' => $vendor->created_at,
            ],
            'admin' => $admin ? [
                'email' => $admin->email,
                'first_name' => $admin->first_name,
                'last_name' => $admin->last_name,
            ] : null,
            'vendor_api_token' => $apiToken,
            'seller_uuid' => $sellerUuid,
        ]);
    }

    /**
     * Find a vendor by its linked soko_seller_uuid setting.
     */
    private function findVendorBySellerUuid(string $sellerUuid): ?VendorModel
    {
        $setting = VendorSettingsModel::where('name', 'soko_seller_uuid')
            ->where('value', $sellerUuid)
            ->first();

        if (!$setting) {
            return null;
        }

        return VendorModel::where('_id', $setting->vendors__id)->first();
    }

    /**
     * Get vendor API token from settings.
     */
    private function getVendorApiToken(int $vendorId): ?string
    {
        $setting = VendorSettingsModel::where('vendors__id', $vendorId)
            ->where('name', 'vendor_api_access_token')
            ->first();

        return $setting ? $setting->value : null;
    }

    /**
     * Store a vendor setting.
     */
    private function storeVendorSetting(int $vendorId, string $name, string $value): void
    {
        $existing = VendorSettingsModel::where('vendors__id', $vendorId)
            ->where('name', $name)
            ->first();

        if ($existing) {
            $existing->value = $value;
            $existing->save();
            return;
        }

        $model = new VendorSettingsModel();
        $model->_uid = (string) Str::uuid();
        $model->vendors__id = $vendorId;
        $model->name = $name;
        $model->value = $value;
        $model->data_type = 1; // string
        $model->status = 1;
        $model->save();
    }
}
