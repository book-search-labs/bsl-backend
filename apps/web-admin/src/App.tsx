import { Navigate, Route, Routes } from "react-router-dom";

import AdminLayout from "./layouts/AdminLayout";
import DashboardPage from "./pages/DashboardPage";
import PlaygroundPage from "./pages/PlaygroundPage";
import RerankPlaygroundPage from "./pages/RerankPlaygroundPage";
import ComparePage from "./pages/ComparePage";
import SettingsPage from "./pages/SettingsPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import OpsJobsPage from "./pages/OpsJobsPage";
import OpsAutocompletePage from "./pages/OpsAutocompletePage";
import ModelOpsPage from "./pages/ModelOpsPage";
import RagOpsPage from "./pages/RagOpsPage";
import RagEvalPage from "./pages/RagEvalPage";
import ProductOpsPage from "./pages/ProductOpsPage";
import PaymentRefundOpsPage from "./pages/PaymentRefundOpsPage";
import ShippingOpsPage from "./pages/ShippingOpsPage";
import AuthorityOpsPage from "./pages/AuthorityOpsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AdminLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="dashboard/v1" element={<DashboardPage />} />
        <Route path="dashboard/v2" element={<DashboardPage />} />
        <Route path="dashboard/v3" element={<DashboardPage />} />
        <Route path="search-playground" element={<PlaygroundPage />} />
        <Route path="rerank-playground" element={<RerankPlaygroundPage />} />
        <Route path="tools">
          <Route path="playground" element={<Navigate to="/search-playground" replace />} />
          <Route path="compare" element={<ComparePage />} />
        </Route>
        <Route path="ops">
          <Route path="index">
            <Route path="indices" element={<PlaceholderPage title="Indices" />} />
            <Route path="doc-lookup" element={<PlaceholderPage title="Doc Lookup" />} />
          </Route>
          <Route path="jobs" element={<OpsJobsPage />} />
          <Route path="autocomplete" element={<OpsAutocompletePage />} />
          <Route path="models" element={<ModelOpsPage />} />
          <Route path="rag" element={<RagOpsPage />} />
          <Route path="rag-eval" element={<RagEvalPage />} />
          <Route path="authority" element={<AuthorityOpsPage />} />
          <Route path="commerce">
            <Route path="products" element={<ProductOpsPage />} />
            <Route path="payments" element={<PaymentRefundOpsPage />} />
            <Route path="shipping" element={<ShippingOpsPage />} />
          </Route>
        </Route>
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
