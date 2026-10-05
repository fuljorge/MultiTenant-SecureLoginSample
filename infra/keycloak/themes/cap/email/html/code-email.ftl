<#-- Validade exibida em minutos (a extensão informa segundos em "ttl"). -->
<#import "template.ftl" as layout>
<@layout.emailLayout>
${kcSanitize(msg("emailCodeBodyHtml", code, (ttl / 60)?ceiling))?no_esc}
</@layout.emailLayout>
