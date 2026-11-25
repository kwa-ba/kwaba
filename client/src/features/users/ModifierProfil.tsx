"use client";

import DeleteAccount from "./DeleteAccount";
import { lireMoi, modifierMoi } from "./api";
import { CLE_MOI } from "./hooks";
import { Link } from "@/i18n/navigation";
import { ArrowLeft, User, Mail, Save } from "lucide-react";
import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";
import { apiErrorMessage } from "@/lib/api";
import { normaliserTelephone } from "@/lib/telephone/telephone";
import PhoneInput, { useErreurTelephone } from "@/components/ui/PhoneInput";
import { useTranslations } from "next-intl";

export default function EditProfilePage() {
  const t = useTranslations("profilEdition");
  const { update } = useSession();
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [erreurTel, setErreurTel] = useState<string>();
  const erreurTelephone = useErreurTelephone();

  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
  });

  useEffect(() => {
    lireMoi()
      .then((moi) => {
        setForm({
          first_name: moi.first_name ?? "",
          last_name: moi.last_name ?? "",
          email: moi.email ?? "",
          phone: moi.phone ?? "",
        });
      })
      .catch(() => setError(t("erreurChargement")))
      .finally(() => setFetching(false));
    // Single load when the page opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const invalide = erreurTelephone(form.phone);
    if (invalide) {
      setErreurTel(invalide);
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(false);
    try {
      const moi = await modifierMoi({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        // Saved numbers in an older format (« +228 90 00 00 00 ») leave in E.164 too
        phone: normaliserTelephone(form.phone) || null,
      });
      setForm((prev) => ({ ...prev, phone: moi.phone ?? "" }));
      await update({ name: `${moi.first_name} ${moi.last_name}` });
      queryClient.invalidateQueries({ queryKey: CLE_MOI });
      setSuccess(true);
    } catch (err) {
      setError(apiErrorMessage(err, t("erreurMaj")));
    } finally {
      setLoading(false);
    }
  };

  if (fetching) {
    return (
      <div className="min-h-screen bg-light flex items-center justify-center">
        <p className="text-muted">{t("chargement")}</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 md:py-12">
      <div className="mb-8 flex items-center gap-4">
        <Link
          href="/profil"
          aria-label={t("retourProfil")}
          className="w-10 h-10 rounded-full bg-surface shadow-xs flex items-center justify-center text-dark hover:bg-light transition-colors"
        >
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="font-heading font-bold text-2xl sm:text-3xl text-dark">{t("titre")}</h1>
          <p className="text-muted text-sm mt-1">{t("sousTitre")}</p>
        </div>
      </div>

      <div className="bg-surface rounded-2xl shadow-card p-5 sm:p-8 md:p-10">
        <form method="post" onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
              {error}
            </div>
          )}
          {success && (
            <div className="bg-green-50 border border-green-200 text-green-700 rounded-xl px-4 py-3 text-sm">
              {t("succes")}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-semibold text-dark mb-1.5 ml-1">{t("prenom")}</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <User size={18} className="text-muted" />
                </div>
                <input
                  type="text"
                  name="first_name"
                  value={form.first_name}
                  onChange={handleChange}
                  className="w-full pl-11 pr-4 py-3 bg-surface border border-gray-200 rounded-xl text-base sm:text-sm text-dark focus:outline-hidden focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all shadow-xs"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-semibold text-dark mb-1.5 ml-1">{t("nom")}</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <User size={18} className="text-muted" />
                </div>
                <input
                  type="text"
                  name="last_name"
                  value={form.last_name}
                  onChange={handleChange}
                  className="w-full pl-11 pr-4 py-3 bg-surface border border-gray-200 rounded-xl text-base sm:text-sm text-dark focus:outline-hidden focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all shadow-xs"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-semibold text-dark mb-1.5 ml-1">{t("email")}</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <Mail size={18} className="text-muted" />
              </div>
              <input
                type="email"
                value={form.email}
                disabled
                className="w-full pl-11 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-muted cursor-not-allowed"
              />
            </div>
            <p className="text-xs text-muted ml-1 mt-1">{t("emailFixe")}</p>
          </div>

          <PhoneInput
            label={t("telephone")}
            labelClassName="block text-sm font-semibold text-dark mb-1.5 ml-1"
            id="phone"
            name="phone"
            value={form.phone}
            onChange={(phone) => {
              setForm((prev) => ({ ...prev, phone }));
              setErreurTel(undefined);
            }}
            error={erreurTel}
          />

          <div className="pt-4 flex flex-col-reverse sm:flex-row sm:justify-end gap-3 border-t border-gray-100 mt-8">
            <Link
              href="/profil"
              className="px-6 py-3 rounded-xl border border-gray-200 text-dark font-medium text-center hover:bg-light-muted transition-colors"
            >
              Annuler
            </Link>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 px-8 py-3 bg-primary text-white rounded-xl font-medium shadow-md hover:bg-primary-600 hover:shadow-lg transition-all disabled:opacity-70"
            >
              <Save size={18} />
              {loading ? t("enregistrement") : t("enregistrer")}
            </button>
          </div>
        </form>
      </div>

      <DeleteAccount />
    </div>
  );
}
