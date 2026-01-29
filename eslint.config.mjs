import globals from "globals";

export default [
    {
        files: ["**/*.js"],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "script",
            globals: {
                ...globals.browser,
                ...globals.jquery,
                Chart: "readonly",
                $: "readonly",
                jQuery: "readonly",
            },
        },
        rules: {
            "no-unused-vars": "warn",
            "no-undef": "error",
        },
    },
];
