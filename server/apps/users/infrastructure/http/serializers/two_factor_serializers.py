from rest_framework import serializers


class TwoFactorCodeSerializer(serializers.Serializer):
    # 6 digits, or a backup code such as 'K7QF-92XM' (spaces and dashes allowed)
    code = serializers.CharField(max_length=20, trim_whitespace=True)


class TwoFactorVerifySerializer(TwoFactorCodeSerializer):
    # The session's refresh token: sent by the Next server, never by the browser
    refresh = serializers.CharField(max_length=2000)


class TwoFactorResetSerializer(serializers.Serializer):
    motif = serializers.CharField(min_length=10, max_length=500, trim_whitespace=True, error_messages={
        'min_length': 'Expliquez le motif de la réinitialisation (10 caractères au moins).',
        'blank': 'Expliquez le motif de la réinitialisation (10 caractères au moins).',
        'required': 'Expliquez le motif de la réinitialisation (10 caractères au moins).',
    })
