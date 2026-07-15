<?php
/**
 * Plugin Name: BlogAuto SEO Meta Bridge
 * Description: Yoast/RankMath/SEOPress의 SEO 메타 키를 WordPress REST API에 노출하여
 *              XML-RPC가 차단된 사이트에서도 BlogAuto가 SEO 메타를 자동 입력할 수 있게 한다.
 * Version: 1.0.0
 * Author: BlogAuto
 *
 * 설치 위치: wp-content/mu-plugins/blogauto-seo-meta.php
 *   (mu-plugins 폴더가 없으면 새로 생성)
 *
 * 동작 원리:
 *   WordPress는 _ (underscore) 로 시작하는 메타 키를 protected meta로 분류하여
 *   REST API 노출을 차단한다. register_post_meta()로 show_in_rest=true를 명시
 *   등록하면 REST API 통로가 열려 외부에서 메타 등록이 가능해진다.
 *
 * 보안:
 *   auth_callback에서 current_user_can('edit_posts') 검증을 적용하여
 *   글 편집 권한이 있는 사용자만 메타를 수정할 수 있다.
 */

if (!defined('ABSPATH')) {
    exit;
}

add_action('init', function () {
    // 메타 수정 권한 검증 (Application Password 보유 사용자가 글 편집 권한 있어야 통과)
    $auth_callback = function () {
        return current_user_can('edit_posts');
    };

    // BlogAuto가 사용하는 SEO 플러그인별 메타 키
    // (한 사이트에서 한 플러그인만 활성화되더라도 모든 키를 미리 등록해두면
    //  플러그인 변경 시에도 추가 작업 없이 호환됨)
    $meta_keys = array(
        // Yoast SEO
        '_yoast_wpseo_focuskw'         => 'string',
        '_yoast_wpseo_metadesc'        => 'string',
        // Rank Math
        'rank_math_focus_keyword'      => 'string',
        'rank_math_description'        => 'string',
        // SEOPress
        '_seopress_analysis_target_kw' => 'string',
        '_seopress_titles_desc'        => 'string',
    );

    foreach ($meta_keys as $key => $type) {
        register_post_meta('post', $key, array(
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => $type,
            'auth_callback' => $auth_callback,
        ));
    }
});
