<?php

return [
    'free' => [ // only one plan, do not change this key
        'id' => 'free', // do not change this id
        'enabled' => true,
        'title' => 'Starter',
        'trial_days' => 0,
        'features' => [
            'contacts' => [
                'description' => __tr('Contacts'),
                'limit' => 25,
            ],
            'campaigns' => [
                'limit_duration' => 'monthly',
                'limit_duration_title' => __tr('Per Month'),
                'description' => __tr('Campaigns'),
                'limit' => 2,
            ],
            'bot_replies' => [
                'description' => __tr('Bot Replies'),
                'limit' => 5,
            ],
            'bot_flows' => [
                'description' => __tr('Bot Flows'),
                'limit' => 1,
            ],
            'contact_custom_fields' => [
                'description' => __tr('Contact Custom Fields'),
                'limit' => 2,
            ],
            'system_users' => [
                'description' => __tr('Team Members/Agents'),
                'limit' => 0,
            ],
            'ai_chat_bot' => [
                'type' => 'switch',
                'description' => __tr('AI Chat Bot'),
                'limit' => 0,
            ],
            'api_access' => [
                'type' => 'switch',
                'description' => __tr('API and Webhook Access'),
                'limit' => 1,
            ],
        ],
    ],
    'paid' => [ // do not change this key
        'plan_1' => [
            'id' => 'plan_1',
            'enabled' => true,
            'popular' => true,
            'title' => 'Growth',
            'trial_days' => 14,
            'features' => [
                'contacts' => [
                    'description' => __tr('Contacts'),
                    'limit' => 500,
                ],
                'campaigns' => [
                    'limit_duration' => 'monthly',
                    'limit_duration_title' => __tr('Per Month'),
                    'description' => __tr('Campaigns'),
                    'limit' => 10,
                ],
                'bot_replies' => [
                    'description' => __tr('Bot Replies'),
                    'limit' => 25,
                ],
                'bot_flows' => [
                    'description' => __tr('Bot Flows'),
                    'limit' => 5,
                ],
                'contact_custom_fields' => [
                    'description' => __tr('Contact Custom Fields'),
                    'limit' => 10,
                ],
                'system_users' => [
                    'description' => __tr('Team Members/Agents'),
                    'limit' => 3,
                ],
                'ai_chat_bot' => [
                    'type' => 'switch',
                    'description' => __tr('AI Chat Bot'),
                    'limit' => 1,
                ],
                'api_access' => [
                    'type' => 'switch',
                    'description' => __tr('API and Webhook Access'),
                    'limit' => 1,
                ],
            ],
            'charges' => [
                'monthly' => [
                    'title' => __tr('monthly'),
                    'enabled' => true,
                    'price_id' => '',
                    'charge' => 5,
                ],
                'yearly' => [
                    'title' => __tr('yearly'),
                    'enabled' => true,
                    'price_id' => '',
                    'charge' => 50,
                ],
            ],
        ],
        'plan_2' => [
            'id' => 'plan_2',
            'enabled' => true,
            'popular' => false,
            'title' => 'Business',
            'trial_days' => 14,
            'features' => [
                'contacts' => [
                    'description' => __tr('Contacts'),
                    'limit' => 5000,
                ],
                'campaigns' => [
                    'limit_duration' => 'monthly',
                    'limit_duration_title' => __tr('Per Month'),
                    'description' => __tr('Campaigns'),
                    'limit' => 50,
                ],
                'bot_replies' => [
                    'description' => __tr('Bot Replies'),
                    'limit' => 100,
                ],
                'bot_flows' => [
                    'description' => __tr('Bot Flows'),
                    'limit' => 20,
                ],
                'contact_custom_fields' => [
                    'description' => __tr('Contact Custom Fields'),
                    'limit' => 25,
                ],
                'system_users' => [
                    'description' => __tr('Team Members/Agents'),
                    'limit' => 10,
                ],
                'ai_chat_bot' => [
                    'type' => 'switch',
                    'description' => __tr('AI Chat Bot'),
                    'limit' => 1,
                ],
                'api_access' => [
                    'type' => 'switch',
                    'description' => __tr('API and Webhook Access'),
                    'limit' => 1,
                ],
            ],
            'charges' => [
                'monthly' => [
                    'title' => __tr('monthly'),
                    'enabled' => true,
                    'price_id' => '',
                    'charge' => 15,
                ],
                'yearly' => [
                    'title' => __tr('yearly'),
                    'enabled' => true,
                    'price_id' => '',
                    'charge' => 150,
                ],
            ],
        ],
        'plan_3' => [
            'id' => 'plan_3',
            'enabled' => true,
            'popular' => false,
            'title' => 'Enterprise',
            'trial_days' => 14,
            'features' => [
                'contacts' => [
                    'description' => __tr('Contacts'),
                    'limit' => -1,
                ],
                'campaigns' => [
                    'limit_duration' => 'monthly',
                    'limit_duration_title' => __tr('Per Month'),
                    'description' => __tr('Campaigns'),
                    'limit' => -1,
                ],
                'bot_replies' => [
                    'description' => __tr('Bot Replies'),
                    'limit' => -1,
                ],
                'bot_flows' => [
                    'description' => __tr('Bot Flows'),
                    'limit' => -1,
                ],
                'contact_custom_fields' => [
                    'description' => __tr('Contact Custom Fields'),
                    'limit' => -1,
                ],
                'system_users' => [
                    'description' => __tr('Team Members/Agents'),
                    'limit' => -1,
                ],
                'ai_chat_bot' => [
                    'type' => 'switch',
                    'description' => __tr('AI Chat Bot'),
                    'limit' => 1,
                ],
                'api_access' => [
                    'type' => 'switch',
                    'description' => __tr('API and Webhook Access'),
                    'limit' => 1,
                ],
            ],
            'charges' => [
                'monthly' => [
                    'title' => __tr('monthly'),
                    'enabled' => true,
                    'price_id' => '',
                    'charge' => 35,
                ],
                'yearly' => [
                    'title' => __tr('yearly'),
                    'enabled' => true,
                    'price_id' => '',
                    'charge' => 350,
                ],
            ],
        ],
    ],
];
